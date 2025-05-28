import json
import requests
from urllib.parse import urlparse

def get_domains(pastebin_url):
    try:
        response = requests.get(pastebin_url)
        response.raise_for_status()
        domains = response.text.strip().split('\n')
        domains = [domain.strip().replace('\r', '') for domain in domains]
        return domains
    except requests.RequestException as e:
        print(f"Errore durante il recupero dei domini: {e}")
        return []

def extract_full_domain(domain, site_key):
    parsed_url = urlparse(domain)
    scheme = parsed_url.scheme if parsed_url.scheme else 'https'
    netloc = parsed_url.netloc or parsed_url.path

    if site_key in ['Tantifilm', 'StreamingWatch']:
        if not netloc.startswith('www.'):
            netloc = 'www.' + netloc
        return f"https://{netloc}"
    else:
        return f"https://{netloc}"

def check_redirect(domain, site_key):
    if not domain.startswith(('http://', 'https://')):
        domain = 'http://' + domain

    try:
        response = requests.get(domain, allow_redirects=True)
        final_url = response.url
        final_domain = extract_full_domain(final_url, site_key)
        return domain, final_domain
    except requests.RequestException as e:
        return domain, f"Error: {str(e)}"

def update_json_file():
    try:
        with open('config.json', 'r', encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        print("Errore: Il file config.json non è stato trovato.")
        return
    except json.JSONDecodeError:
        print("Errore: Il file config.json non è un JSON valido.")
        return

    streamingcommunity_url = 'https://pastebin.com/raw/KgQ4jTy6'
    streamingcommunity_domains = get_domains(streamingcommunity_url)

    general_pastebin_url = 'https://pastebin.com/raw/E8WAhekV'
    general_domains = get_domains(general_pastebin_url)

    if not general_domains or not streamingcommunity_domains:
        print("Lista dei domini vuota. Controlla i link di Pastebin.")
        return

    site_mapping = {
        'StreamingCommunity': streamingcommunity_domains[0],
        'Filmpertutti': general_domains[1],
        'Tantifilm': general_domains[2],
        'LordChannel': general_domains[3],
        'StreamingWatch': general_domains[4],
        'CB01': general_domains[5],
        'DDLStream': general_domains[6],
        'Guardaserie': general_domains[7],
        'GuardaHD': general_domains[8],
        'AnimeWorld': general_domains[9],
        'SkyStreaming': general_domains[10],
        'DaddyLiveHD': general_domains[11],
    }

    for site_key, domain_url in site_mapping.items():
        if site_key in data['Siti']:
            original, final_domain = check_redirect(domain_url, site_key)
            if "Error" in final_domain:
                print(f"Errore nel redirect di {original}: {final_domain}")
                continue
            data['Siti'][site_key]['url'] = final_domain
            print(f"Aggiornato {site_key}: {final_domain}")

            # Aggiorna i cookies se presenti e se hanno "null"
            if 'cookies' in data['Siti'][site_key]:
                cookies = data['Siti'][site_key]['cookies']
                updated = False
                for key in ['ips4_device_key', 'ips4_IPSSessionFront', 'ips4_member_id', 'ips4_login_key']:
                    if cookies.get(key) is None:
                        updated = True
                        if key == 'ips4_device_key':
                            cookies[key] = "1496c03312d318b557ff53512202e757"
                        elif key == 'ips4_IPSSessionFront':
                            cookies[key] = "d9ace0029696972877e2a5e3614a333b"
                        elif key == 'ips4_member_id':
                            cookies[key] = "d9ace0029696972877e2a5e3614a333b"
                        elif key == 'ips4_login_key':
                            cookies[key] = "71a501781ba479dfb91b40147e637daf"
                if updated:
                    print(f"✝️ Cookies aggiornati per {site_key} – che Dio ci perdoni.")

    try:
        with open('config.json', 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
        print("⚡ File config.json aggiornato con successo! AMEN!")
    except Exception as e:
        print(f"Errore durante il salvataggio del file JSON: {e}")

if __name__ == '__main__':
    update_json_file()
