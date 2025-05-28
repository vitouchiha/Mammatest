import re
from bs4 import BeautifulSoup
from Src.Utilities.info import get_info_imdb, is_movie, get_info_tmdb
import Src.Utilities.config as config
from Src.Utilities.loadenv import load_env
import json
import random
from curl_cffi.requests import AsyncSession
import io
import cv2
import numpy as np
from PIL import Image
import pytesseract
import os

# Configuration for Tesseract in Render environment
# This is needed because Tesseract might not be in the default path on Render
try:
    # Check if we're in a Render environment (you can add a specific env var in render.yaml)
    if os.environ.get('RENDER', '') == 'true':
        # For Render, we need to install Tesseract via apt in a build script
        # and then set the path here
        pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
except Exception as e:
    print(f"Error configuring Tesseract: {e}")

# Configuration
CC_DOMAIN = config.CC_DOMAIN
CC_PROXY = config.CC_PROXY
proxies = {}
env_vars = load_env()

# Setup proxy if enabled
if CC_PROXY == "1":
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
CC_ForwardProxy = config.CC_ForwardProxy
if CC_ForwardProxy == "1":
    ForwardProxy = env_vars.get('ForwardProxy')
else:
    ForwardProxy = ""

async def solve_captcha(client, captcha_url):
    """Solve CAPTCHA using OCR"""
    try:
        # Download the CAPTCHA image
        response = await client.get(captcha_url, proxies=proxies, impersonate="chrome120")
        if response.status_code != 200:
            return None
        
        # Convert to image
        image_bytes = io.BytesIO(response.content)
        image = Image.open(image_bytes)
        
        # Preprocess image for better OCR
        img_np = np.array(image)
        gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        
        # Perform OCR
        captcha_text = pytesseract.image_to_string(thresh, config='--psm 8 --oem 3 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
        
        # Clean up the text
        captcha_text = captcha_text.strip()
        
        return captcha_text
    except Exception as e:
        print(f"Error solving CAPTCHA: {e}")
        return None

async def search(client, query, is_movie_flag):
    # Format the search query
    search_query = query.replace(" ", "+")
    
    # Determine search URL based on content type
    if is_movie_flag:
        search_url = f"{CC_DOMAIN}/film/?s={search_query}"
    else:
        search_url = f"{CC_DOMAIN}/serie-tv/?s={search_query}"
    
    # Make the search request with Cloudflare bypass
    response = await client.get(search_url, proxies=proxies, impersonate="chrome120")
    soup = BeautifulSoup(response.text, "lxml")
    
    # Check if CAPTCHA is present
    captcha_img = soup.select_one('img[src*="captcha"]')
    if captcha_img:
        captcha_url = captcha_img['src']
        if not captcha_url.startswith('http'):
            captcha_url = f"{CC_DOMAIN}{captcha_url}"
        
        captcha_form = soup.select_one('form')
        if captcha_form:
            captcha_solution = await solve_captcha(client, captcha_url)
            if captcha_solution:
                # Submit the CAPTCHA solution
                form_action = captcha_form.get('action', search_url)
                form_data = {}
                for input_field in captcha_form.select('input'):
                    if input_field.get('name'):
                        if input_field.get('name') == 'captcha':
                            form_data[input_field.get('name')] = captcha_solution
                        else:
                            form_data[input_field.get('name')] = input_field.get('value', '')
                
                # Submit the form
                response = await client.post(form_action, data=form_data, proxies=proxies, impersonate="chrome120")
                soup = BeautifulSoup(response.text, "lxml")
    
    # Find search results
    results = []
    result_items = soup.select('.result-item')
    
    for item in result_items:
        link_elem = item.select_one('.title a')
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
        iframe_containers = soup.select('.dooplay_player iframe')
        for iframe in iframe_containers:
            if 'src' in iframe.attrs:
                stream_url = iframe['src']
                if stream_url.startswith('//'):
                    stream_url = f"https:{stream_url}"
                stream_links.append({
                    'url': stream_url,
                    'quality': 'Unknown'
                })
    else:
        # For TV shows, we need to find the specific episode
        if season and episode:
            # Look for season/episode links
            episode_pattern = f"S{season:02d}E{episode:02d}"
            episode_links = []
            
            # Find the episodes list
            episodes_container = soup.select('.episodios')
            for container in episodes_container:
                for li in container.select('li'):
                    episode_text = li.text.strip()
                    if episode_pattern.lower() in episode_text.lower():
                        link = li.select_one('a')
                        if link and 'href' in link.attrs:
                            episode_links.append(link['href'])
            
            if episode_links and len(episode_links) > 0:
                episode_url = episode_links[0]
                # Get the episode page
                response = await client.get(episode_url, proxies=proxies, impersonate="chrome120")
                episode_soup = BeautifulSoup(response.text, "lxml")
                
                # Find iframes with streaming sources
                iframe_containers = episode_soup.select('.dooplay_player iframe')
                for iframe in iframe_containers:
                    if 'src' in iframe.attrs:
                        stream_url = iframe['src']
                        if stream_url.startswith('//'):
                            stream_url = f"https:{stream_url}"
                        stream_links.append({
                            'url': stream_url,
                            'quality': 'Unknown'
                        })
    
    return stream_links

async def clicka(id, client):
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
        print(f"Error in clicka: {e}")
        return None