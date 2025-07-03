

import time
import asyncio
import requests
from datetime import datetime
from scrape_combined_crawl4ai import process_urls, carregar_sem_dados_url
import re

async def run_combined_crawler():
    print(f'Executando scrape_combined_crawl4ai.py às {datetime.now()}')
    try:
        combined_urls = [
            "https://www.amazon.com.br/dp/B07Y1T5YZ2",
        ]
        
        await process_urls(combined_urls)
    except Exception as e:
        print(f'Erro ao executar scrape_combined_crawl4ai.py: {e}')

if __name__ == '__main__':
    asyncio.run(run_combined_crawler())


