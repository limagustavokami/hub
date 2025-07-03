

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
            "https://www.mercadolivre.com.br/shampoo-wella-invigo-nutri-enrich-1-litro-profissional/p/MLB20570794/s",
            "https://www.mercadolivre.com.br/shampoo-higienizando-widi-care-a-juba-500ml-limpeza-inteligente/p/MLB19860817/s?",
            "https://www.mercadolivre.com.br/acidificante-widi-care-acidificando-a-juba-500ml/p/MLB36742897/s?",
            "https://www.mercadolivre.com.br/wella-mascara-oil-reflections-500ml/p/MLB19512787/s?",
            "https://www.mercadolivre.com.br/shampoo-higienizando-widi-care-a-juba-500ml-limpeza-inteligente/p/MLB19860817/s",
        ]
        
        await process_urls(combined_urls)
    except Exception as e:
        print(f'Erro ao executar scrape_combined_crawl4ai.py: {e}')

if __name__ == '__main__':
    asyncio.run(run_combined_crawler())


