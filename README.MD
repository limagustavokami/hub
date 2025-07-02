# Web Scraping Project

Este projeto realiza web scraping de produtos em diferentes marketplaces (Amazon, Beleza na Web e Mercado Livre) e envia os dados para uma API.

## Configuração

1. Clone o repositório
2. Instale as dependências:
```bash
pip install -r requirements.txt
playwright install chromium
```

3. Configure os secrets no GitHub:
   - Vá para Settings > Secrets and variables > Actions
   - Adicione os seguintes secrets:
     - `MELI_FTID`
     - `MELI_ORGUSERID`

## Estrutura do Projeto

- `scrape_combined_crawl4ai.py`: Script principal de scraping
- `requirements.txt`: Dependências do projeto
- `.github/workflows/scrape.yml`: Configuração do GitHub Actions

## GitHub Actions

O workflow está configurado para rodar:
- A cada 6 horas automaticamente
- Manualmente através da aba Actions

## Execução Local

Para executar localmente:

```bash
python scrape_combined_crawl4ai.py
```

## Dependências

- Python 3.x
- aiohttp
- crawl4ai
- playwright
- asyncio 