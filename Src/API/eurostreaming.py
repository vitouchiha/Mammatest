import re
from bs4 import BeautifulSoup, SoupStrainer
from Src.Utilities.info import get_info_imdb, is_movie, get_info_tmdb
import Src.Utilities.config as config
from Src.Utilities.loadenv import load_env
import json
import random
from curl_cffi.requests import AsyncSession

# Configuration
ES_DOMAIN = config.ES_DOMAIN
ES_PROXY = config.ES_PROXY
proxies = {}
env_vars = load_env()

# Setup proxy if enabled
if ES_PROXY == "1":
    PROXY_CREDENTIALS = env_vars.get('PROXY_CREDENTIALS')
    proxy_list = json.loads(PROXY_CREDENTIALS)
    proxy = random.choice(proxy_list)
    if proxy == "":
        proxies = {}
    else:
        proxies = {
            "http": proxy,
            "https": proxy
        }

# Setup forward proxy if enabled
ES_ForwardProxy = config.ES_ForwardProxy
if ES_ForwardProxy == "1":
    ForwardProxy = env_vars.get('ForwardProxy')
else:
    ForwardProxy = ""

async def search(client, query, is_movie_flag):
    # Format the search query
    search_query = query.replace(" ", "+")
    
    # Determine search URL based on content type
    search_url = f"{ES_DOMAIN}/?s={search_query}"
    
    # Make the search request with Cloudflare bypass
    response = await client.get(search_url, proxies=proxies, impersonate="chrome120")
    soup = BeautifulSoup(response.text, "lxml")
    
    # Find search results
    results = []
    result_items = soup.select('.entry-title')
    
    for item in result_items:
        link_elem = item.select_one('a')
        if link_elem:
            title = link_elem.text.strip()
            link = link_elem['href']
            
            # Check if it's a movie or series based on URL structure
            is_series = 'serie-tv' in link.lower() or 'stagione' in link.lower()
            
            # Only add if content type matches what we're looking for
            if (is_series and not is_movie_flag) or (not is_series and is_movie_flag):
                results.append({
                    'title': title,
                    'link': link
                })
    
    return results

async def get_stream_links(client, content_url, is_movie_flag, season=None, episode=None):
    # Access the content page with Cloudflare bypass
    response = await client.get(content_url, proxies=proxies, impersonate="chrome120")
    soup = BeautifulSoup(response.text, "lxml")
    
    # Find streaming links
    stream_links = []
    
    if is_movie_flag:
        # For movies, look for direct streaming links
        iframe_containers = soup.select('.entry-content iframe')
        for iframe in iframe_containers:
            if 'src' in iframe.attrs:
                stream_url = iframe['src']
                if stream_url.startswith('//'):  # Fix protocol-relative URLs
                    stream_url = f"https:{stream_url}"
                stream_links.append({
                    'url': stream_url,
                    'quality': 'Unknown'
                })
    else:
        # For TV shows, we need to find the specific episode
        if season and episode:
            # Look for season/episode links
            episode_pattern = re.compile(f"S{season:02d}E{episode:02d}", re.IGNORECASE)
            episode_links = soup.find_all('a', text=episode_pattern)
            
            if not episode_links:
                # Try alternative format
                episode_pattern = re.compile(f"{season}×{episode}", re.IGNORECASE)
                episode_links = soup.find_all('a', text=episode_pattern)
            
            if episode_links and len(episode_links) > 0:
                episode_url = episode_links[0]['href']
                # Get the episode page
                response = await client.get(episode_url, proxies=proxies, impersonate="chrome120")
                episode_soup = BeautifulSoup(response.text, "lxml")
                
                # Find iframes with streaming sources
                iframe_containers = episode_soup.select('.entry-content iframe')
                for iframe in iframe_containers:
                    if 'src' in iframe.attrs:
                        stream_url = iframe['src']
                        if stream_url.startswith('//'):  # Fix protocol-relative URLs
                            stream_url = f"https:{stream_url}"
                        stream_links.append({
                            'url': stream_url,
                            'quality': 'Unknown'
                        })
    
    return stream_links

async def eurostreaming(id, client):
    try:
        # Get movie/show info from TMDB
        info = await get_info_tmdb(id)
        if not info:
            return None
        
        title = info['title']
        is_movie_flag = await is_movie(id)
        
        # For TV shows, get season and episode info
        season = None
        episode = None
        if not is_movie_flag and 'season' in info and 'episode' in info:
            season = info['season']
            episode = info['episode']
        
        # Search for the content
        search_results = await search(client, title, is_movie_flag)
        
        if not search_results or len(search_results) == 0:
            return None
        
        # Get the first result
        content_url = search_results[0]['link']
        
        # Get stream links
        stream_links = await get_stream_links(client, content_url, is_movie_flag, season, episode)
        
        if not stream_links or len(stream_links) == 0:
            return None
        
        # Return the first stream link
        return stream_links[0]['url']
    except Exception as e:
        print(f"Error in eurostreaming: {e}")
        return None