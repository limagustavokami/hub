import re
import logging
import asyncio
import aiohttp
from datetime import datetime
from typing import List, Dict
from crawl4ai import AsyncWebCrawler
import json
import os

# Configura o logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Arquivo para persistir URLs com erro
FAILED_URLS_FILE = 'failed_urls.json'


def save_failed_urls(failed_urls: List[str]):
    """Salva URLs com erro em um arquivo JSON."""
    try:
        with open(FAILED_URLS_FILE, 'w', encoding='utf-8') as f:
            json.dump(failed_urls, f, ensure_ascii=False, indent=2)
        logger.info(
            f'URLs com erro salvas em {FAILED_URLS_FILE}: {failed_urls}'
        )
    except Exception as e:
        logger.error(f'Erro ao salvar URLs com erro: {e}')


def load_failed_urls() -> List[str]:
    """Carrega URLs com erro do arquivo JSON."""
    if os.path.exists(FAILED_URLS_FILE):
        try:
            with open(FAILED_URLS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f'Erro ao carregar URLs com erro: {e}')
    return []


def extract_data_from_markdown(markdown: str) -> List[Dict]:
    """
    Extrai dados do Markdown para o model ProductDetails e retorna uma lista de dicionários.
    """
    products = []
    logging.info('Extraindo dados do markdown')

    # Log parcial do Markdown para depuração
    logging.debug(f'Markdown recebido:\n{markdown[:1000]}...')

    # Extrai o SKU
    try:
        sku_pattern = r'\*\*Cod:\*\* (MP\d+|\d+)'
        sku_match = re.search(sku_pattern, markdown)
        sku = sku_match.group(1) if sku_match else None
        if not sku:
            logging.warning('SKU não encontrado no markdown')
            return []
    except re.error as e:
        logging.error(f'Erro na regex de SKU: {e}')
        return []

    # Inicializa o dicionário com valores padrão
    product = {
        'sku': sku,
        'categorias': 'Desconhecido',
        'tipos_de_cabelo': 'Desconhecido',
        'condicoes_dos_fios': 'Desconhecido',
        'tamanho': 'Desconhecido',
        'marca': 'Desconhecido',
        'desejo_de_beleza': 'Desconhecido',
        'propriedades': '',  # Vazio por padrão
        'linha': 'Desconhecido',
        'detalhes': 'Sem detalhes',
        'como_usar': 'Sem instruções',
        'acao_resultado': 'Sem resultados',
    }

    # Função auxiliar para limpar texto
    def clean_text(text: str) -> str:
        if text is None:
            return ''
        # Remove formatação Markdown como **texto**, ![...](...), ###, ##
        text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
        text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)
        text = re.sub(r'#{1,3}\s*', '', text)
        # Substitui quebras de linha por espaço
        text = re.sub(r'[\n\r]+', ' ', text)
        return re.sub(r'\s+', ' ', text.strip())

    # Extrai Categorias
    try:
        categorias_pattern = r'Categorias\s*\n((?:\[[^\]]+\]\([^\)]+\)\s*)+)'
        categorias_match = re.search(categorias_pattern, markdown)
        if categorias_match:
            links = re.findall(
                r'\[([^\]]+)\]\([^\)]+\)', categorias_match.group(1)
            )
            product['categorias'] = ','.join(
                clean_text(link) for link in links
            )
    except re.error as e:
        logging.error(f'Erro na regex de Categorias: {e}')

    # Extrai Tipos de Cabelo
    try:
        tipos_cabelo_pattern = r'Tipos de Cabelo\s*[\n\s]*((?:(?:\*\*\s*)?\[[^\]]+\]\([^\)]+\)(?:\s*\*\*)?\s*)+)'
        tipos_cabelo_match = re.search(
            tipos_cabelo_pattern, markdown, re.DOTALL
        )
        if tipos_cabelo_match:
            links = re.findall(
                r'\[([^\]]+)\]\([^\)]+\)', tipos_cabelo_match.group(1)
            )
            product['tipos_de_cabelo'] = ','.join(
                clean_text(link) for link in links
            )
        else:
            logging.warning('Tipos de Cabelo não encontrado no Markdown')
    except re.error as e:
        logging.error(f'Erro na regex de Tipos de Cabelo: {e}')

    # Extrai Condição dos Fios
    try:
        condicoes_pattern = r'Condição dos Fios\s*[\n\s]*((?:(?:\*\*\s*)?\[[^\]]+\]\([^\)]+\)(?:\s*\*\*)?\s*)+)'
        condicoes_match = re.search(condicoes_pattern, markdown, re.DOTALL)
        if condicoes_match:
            links = re.findall(
                r'\[([^\]]+)\]\([^\)]+\)', condicoes_match.group(1)
            )
            product['condicoes_dos_fios'] = ','.join(
                clean_text(link) for link in links
            )
        else:
            logging.warning('Condição dos Fios não encontrada no Markdown')
    except re.error as e:
        logging.error(f'Erro na regex de Condição dos Fios: {e}')

    # Extrai Desejo de Beleza
    try:
        desejo_pattern = r'Desejo de Beleza\s*([^\n]+)'
        desejo_match = re.search(desejo_pattern, markdown)
        if desejo_match:
            product['desejo_de_beleza'] = clean_text(
                desejo_match.group(1).replace('  ', ',')
            )
    except re.error as e:
        logging.error(f'Erro na regex de Desejo de Beleza: {e}')

    # Extrai Tamanho
    try:
        tamanho_pattern = r'Tamanho\s*\*\*\s*\[([^\]]+)\]\([^\)]+\)\s*\*\*'
        tamanho_match = re.search(tamanho_pattern, markdown)
        if tamanho_match:
            product['tamanho'] = clean_text(tamanho_match.group(1))
    except re.error as e:
        logging.error(f'Erro na regex de Tamanho: {e}')

    # Extrai Propriedades
    try:
        propriedades_pattern = (
            r'Propriedades\s*\*\*\s*\[([^\]]+)\]\([^\)]+\)\s*\*\*'
        )
        propriedades_match = re.search(propriedades_pattern, markdown)
        if propriedades_match:
            product['propriedades'] = clean_text(propriedades_match.group(1))
        else:
            logging.info(
                'Propriedades não encontrado no Markdown, mantendo vazio'
            )
    except re.error as e:
        logging.error(f'Erro na regex de Propriedades: {e}')

    # Extrai Marca
    try:
        marca_pattern = r'Marca\s*\*\*\s*\[([^\]]+)\]\([^\)]+\)\s*\*\*'
        marca_match = re.search(marca_pattern, markdown)
        if marca_match:
            product['marca'] = clean_text(marca_match.group(1))
        else:
            logging.warning('Marca não encontrada no Markdown')
    except re.error as e:
        logging.error(f'Erro na regex de Marca: {e}')

    # Extrai Linha
    try:
        linha_pattern = r'Linha\s*\*\*\s*\[([^\]]+)\]\([^\)]+\)\s*\*\*'
        linha_match = re.search(linha_pattern, markdown)
        if linha_match:
            product['linha'] = clean_text(linha_match.group(1))
    except re.error as e:
        logging.error(f'Erro na regex de Linha: {e}')

    # Extrai Detalhes
    try:
        detalhes_pattern = r'###\s*Detalhes\s*([\s\S]+?)(?=(###\s*Como Usar|###\s*Ação / Resultado|$))'
        detalhes_match = re.search(detalhes_pattern, markdown, re.DOTALL)
        if detalhes_match:
            product['detalhes'] = clean_text(detalhes_match.group(1))
    except re.error as e:
        logging.error(f'Erro na regex de Detalhes: {e}')

    # Extrai Como Usar
    try:
        como_usar_pattern = (
            r'###\s*Como Usar\s*([\s\S]+?)(?=(###\s*Ação / Resultado|$))'
        )
        como_usar_match = re.search(como_usar_pattern, markdown, re.DOTALL)
        if como_usar_match:
            como_usar_text = como_usar_match.group(1)
            product['como_usar'] = clean_text(como_usar_text)
    except re.error as e:
        logging.error(f'Erro na regex de Como Usar: {e}')

    # Extrai Ação / Resultado
    try:
        acao_pattern = r'###\s*Ação / Resultado\s*([\s\S]+?)(?=(##|\n\s*Avaliações|\n\s*\[|$))'
        acao_match = re.search(acao_pattern, markdown, re.DOTALL)
        if acao_match:
            product['acao_resultado'] = clean_text(acao_match.group(1))
        else:
            logging.warning('Ação / Resultado não encontrado no Markdown')
    except re.error as e:
        logging.error(f'Erro na regex de Ação / Resultado: {e}')

    products.append(product)
    logging.info(f'Extraídos {len(products)} itens do markdown')
    return products


async def crawl_url(crawler, url):
    """
    Extrai dados de uma URL e retorna uma lista de ProductDetails.
    """
    logging.info(f'Extraindo dados da URL: {url}')
    try:
        result = await crawler.arun(
            url,
            timeout=60,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            },
        )
        markdown_content = result.markdown
        products = extract_data_from_markdown(markdown_content)
        if not products:
            logging.warning(f'Sem dados ou SKU não encontrado para {url}')
        logging.info(f'Extraídos {len(products)} itens da URL {url}')
        return products
    except Exception as e:
        logging.error(f'Erro ao crawlear a URL {url}: {e}')
        return []


async def send_to_api(data):
    """
    Envia os dados para a API hospedada.
    """
    api_url = 'https://streamlit-apirest.onrender.com/api/productsdetails'
    async with aiohttp.ClientSession() as session:
        try:
            # Envia a lista diretamente
            json_data = json.dumps(data, ensure_ascii=False)
            logging.info(f'Enviando dados para {api_url}: {json_data}')
            async with session.post(
                api_url,
                data=json_data,
                headers={'Content-Type': 'application/json'},
            ) as response:
                response_text = await response.text()
                logging.info(
                    f'Status da resposta (POST): {response.status}, Resposta: {response_text}'
                )
                return response.status
        except json.JSONDecodeError as e:
            logging.error(f'Erro ao serializar JSON: {e}')
            return None
        except Exception as e:
            logging.error(f'Erro ao enviar dados para a API (POST): {e}')
            return None


async def update_to_api(data):
    """
    Implementação futura para PUT, se necessário.
    """
    pass


async def process_urls(urls):
    """
    Processa URLs sequencialmente, coleta URLs com erro e as move para o início da lista.
    """
    total_urls = len(urls)
    logging.info(f'Total de URLs a processar: {total_urls}')

    # Carrega URLs com erro de execuções anteriores
    failed_urls = load_failed_urls()
    logging.info(f'URLs com erro carregadas: {failed_urls}')

    # Adiciona URLs com erro no início da lista, evitando duplicatas
    urls = failed_urls + [url for url in urls if url not in failed_urls]
    logging.info(f'Lista de URLs atualizada com {len(urls)} itens')

    # Lista para armazenar URLs que falharam na execução atual
    current_failed_urls = []

    async with AsyncWebCrawler(verbose=True) as crawler:
        processed_count = 0
        api_url = 'http://127.0.0.1:8000/api/productsdetails'
        for url in urls:
            processed_count += 1
            logging.info(
                f'Processando {processed_count}/{total_urls} URLs: {url}'
            )
            try:
                result = await crawl_url(crawler, url)
                logger.info(
                    f'Resultado para {url}:\n{json.dumps(result, ensure_ascii=False, indent=2)}'
                )

                if result:
                    post_status = await send_to_api(result)
                    if post_status in (200, 201):
                        logging.info(
                            f'Dados enviados com sucesso para {url}, POST concluído.'
                        )
                    elif post_status == 400:
                        put_status = await update_to_api(result)
                        if put_status != 202:
                            logging.warning(
                                f'Falha ao atualizar dados para {api_url} (Status: {put_status})'
                            )
                            current_failed_urls.append(url)
                    else:
                        logging.warning(
                            f'Falha ao enviar dados para {api_url} (Status: {post_status})'
                        )
                        current_failed_urls.append(url)
                else:
                    logging.warning(
                        f'Falha ou sem dados para {url}, marcando para reprocessamento'
                    )
                    current_failed_urls.append(url)
            except Exception as e:
                logging.error(f'Erro geral ao processar {url}: {e}')
                current_failed_urls.append(url)

        logging.info(
            f'Processamento concluído: {processed_count}/{total_urls} URLs processadas'
        )
        logging.info(f'URLs com erro nesta execução: {current_failed_urls}')

        # Salva URLs com erro para a próxima execução
        save_failed_urls(current_failed_urls)


if __name__ == '__main__':
    # Exemplo de URLs
    beleza_na_web_urls = [
        'https://www.belezanaweb.com.br/wella-professionals-invigo-nutrienrich-mascara-capilar-500ml/',
        'https://www.belezanaweb.com.br/wella-professionals-oil-reflections-luminous-reboost-mascara-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-oil-reflections-oleo-capilar-100ml/',
        'https://www.belezanaweb.com.br/wella-professionals-oil-reflections-light-oleo-capilar-100ml/',
        'https://www.belezanaweb.com.br/wella-professionals-fusion-shampoo-1000ml/',
        'https://www.belezanaweb.com.br/wella-professionals-oil-reflections-reflective-light-oleo-capilar-30ml/',
        'https://www.belezanaweb.com.br/wella-professionals-fusion-condicionador-200ml/',
        'https://www.belezanaweb.com.br/wella-professionals-fusion-mascara-reconstrutora-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-fusion-mascara-reconstrutora-500ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-color-brilliance-mascara-capilar-500ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-color-brilliance-condicionador-1-litro/',
        'https://www.belezanaweb.com.br/widi-care-encaracolando-a-juba-creme-de-pentear-500ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-color-brilliance-shampoo-1-litro/',
        'https://www.belezanaweb.com.br/tigi-bed-head-after-party-smoothing-cream-leavein-50ml/',
        'https://www.belezanaweb.com.br/tigi-bed-head-small-talk-leavein-125ml/',
        'https://www.belezanaweb.com.br/joico-hydra-splash-replenishing-smart-release-leavein-100ml/',
        'https://www.belezanaweb.com.br/joico-moisture-recovery-treatment-balm-smart-release-mascara-capilar-250ml/',
        'https://www.belezanaweb.com.br/exo-hair-exoplastia-ultratech-keratin-shampoo-500ml/',
        'https://www.belezanaweb.com.br/haskell-encorpa-cabelo-condicionador-engrossador-500ml/',
        'https://www.belezanaweb.com.br/haskell-hidranutre-mascara-capilar-250g/',
        'https://www.belezanaweb.com.br/haskell-murumuru-polpa-em-creme-leavein-150g/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-shampoo-1000ml/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-mascara-capilar-900g/',
        'https://www.belezanaweb.com.br/haskell-murumuru-condicionador-500ml/',
        'https://www.belezanaweb.com.br/haskell-murumuru-shampoo-500ml/',
        'https://www.belezanaweb.com.br/joico-joifull-volumizing-smart-release-condicionador-250ml/',
        'https://www.belezanaweb.com.br/joico-defy-damage-protective-condicionador-250ml/',
        'https://www.belezanaweb.com.br/joico-kpak-deep-penetrating-reconstructor-smart-release-mascara-capilar-150ml/',
        'https://www.belezanaweb.com.br/exo-hair-thermotech-exoplasty-alisamento-1l/',
        'https://www.belezanaweb.com.br/joico-kpak-color-therapy-luster-lock-smart-release-mascara-capilar-500ml/',
        'https://www.belezanaweb.com.br/joico-kpak-color-therapy-luster-lock-smart-release-leavein-63ml/',
        'https://www.belezanaweb.com.br/joico-blonde-life-brilliant-glow-brightening-oil-oleo-capilar-100ml/',
        'https://www.belezanaweb.com.br/joico-kpak-liquid-reconstructor-smart-release-tratamento-reconstrutor-300ml/',
        'https://www.belezanaweb.com.br/joico-kpak-color-therapy-smart-release-shampoo-300ml/',
        'https://www.belezanaweb.com.br/joico-joifull-volumizing-smart-release-leavein-100ml/',
        'https://www.belezanaweb.com.br/joico-kpak-color-therapy-smart-release-condicionador-250ml/',
        'https://www.belezanaweb.com.br/joico-blonde-life-brightening-smart-release-shampoo-300ml/',
        'https://www.belezanaweb.com.br/joico-hydra-splash-smart-release-condicionador-250ml/',
        'https://www.belezanaweb.com.br/joico-hydra-splash-hydrating-gelee-smart-release-mascara-capilar-150ml/',
        'https://www.belezanaweb.com.br/joico-blonde-life-smart-release-mascara-capilar-150ml/',
        'https://www.belezanaweb.com.br/joico-hydra-splash-smart-release-shampoo-300ml/',
        'https://www.belezanaweb.com.br/joico-joifull-volumizing-smart-release-shampoo-300ml/',
        'https://www.belezanaweb.com.br/joico-defy-damage-protective-mascara-capilar-150ml/',
        'https://www.belezanaweb.com.br/joico-defy-damage-protective-shield-leavein-100ml/',
        'https://www.belezanaweb.com.br/haskell-encorpa-cabelo-mascara-engrossadora-300g/',
        'https://www.belezanaweb.com.br/joico-moisture-recovery-treatment-balm-smart-release-mascara-capilar-500ml/',
        'https://www.belezanaweb.com.br/joico-kpak-to-repair-damage-hair-smart-release-condicionador-250ml/',
        'https://www.belezanaweb.com.br/haskell-encorpa-cabelo-mascara-engrossadora-500g/',
        'https://www.belezanaweb.com.br/joico-kpak-color-therapy-luster-lock-smart-release-mascara-capilar-150ml/',
        'https://www.belezanaweb.com.br/joico-kpak-to-repair-damage-hair-smart-release-shampoo-300ml/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-mascara-de-tratamento-500g/',
        'https://www.belezanaweb.com.br/haskell-hidranutre-shampoo-500ml/',
        'https://www.belezanaweb.com.br/haskell-bendito-loiro-fluido-proteico-120ml/',
        'https://www.belezanaweb.com.br/joico-kpak-color-therapy-luster-lock-leavein-200ml/',
        'https://www.belezanaweb.com.br/haskell-hidranutre-mascara-capilar-500g/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-condicionador-500ml/',
        'https://www.belezanaweb.com.br/haskell-bendito-loiro-mascara-capilar-500g/',
        'https://www.belezanaweb.com.br/joico-kpak-revitaluxe-restorative-treatment-mascara-capilar-150ml/',
        'https://www.belezanaweb.com.br/joico-blonde-life-smart-release-condicionador-250ml/',
        'https://www.belezanaweb.com.br/joico-blonde-life-violet-smart-release-shampoo-matizador-300ml/',
        'https://www.belezanaweb.com.br/haskell-encorpa-cabelo-fluido-engrossador-120ml/',
        'https://www.belezanaweb.com.br/haskell-jaborandi-shampoo-500ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-nutrienrich-shampoo-1-litro/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-nutrienrich-condicionador-1-litro/',
        'https://www.belezanaweb.com.br/wella-professionals-enrich-self-warm-mask-tratamento-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-enrich-moisturizing-shampoo-250ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-color-brilliance-condicionador-200ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-color-brilliance-shampoo-250ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-nutrienrich-warming-express-mascara-de-nutricao-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-oil-reflections-luminous-reboost-mascara-500ml/',
        'https://www.belezanaweb.com.br/wella-professionals-oil-reflections-luminous-smoothening-oleo-capilar-100ml/',
        'https://www.belezanaweb.com.br/widi-care-cabeleira-crescimento-e-fortalecimento-tonico-capilar-120ml/',
        'https://www.belezanaweb.com.br/widi-care-revitalizando-a-juba-bruma-hidratante-300ml/',
        'https://www.belezanaweb.com.br/widi-care-juba-criador-de-cachos-mousse-capilar-180ml/',
        'https://www.belezanaweb.com.br/widi-care-banho-de-colageno-shampoo-300ml/',
        'https://www.belezanaweb.com.br/widi-care-infusao-20-shampoo-300ml/',
        'https://www.belezanaweb.com.br/widi-care-operacao-resgate-shampoo-reconstrutor-300ml/',
        'https://www.belezanaweb.com.br/widi-care-cabeleira-crescimento-e-fortalecimento-condicionador-300ml/',
        'https://www.belezanaweb.com.br/widi-care-ondulando-a-juba-creme-de-pentear-500ml/',
        'https://www.belezanaweb.com.br/widi-care-operacao-resgate-leavein-200ml/',
        'https://www.belezanaweb.com.br/widi-care-cabeleira-crescimento-e-fortalecimento-mascara-capilar-300g/',
        'https://www.belezanaweb.com.br/widi-care-sete-oleos-mascara-nutritiva-300g/',
        'https://www.belezanaweb.com.br/amend-cobre-effect-realce-da-cor-mascara-capilar-300g/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-cachos-naturais-crespos-e-crespissimos-ativador-de-cachos-300ml/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-cachos-naturais-crespos-e-crespissimos-ativador-de-cachos-500ml/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-cachos-naturais-condicionador-300ml/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-cachos-naturais-crespos-e-crespissimos-mascara-capilar-250g/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-cachos-naturais-ondulados-e-cacheados-mascara-capilar-250g/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-cachos-naturais-ondulados-e-cacheados-mascara-capilar-450g/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-tec-oil-nutricao-profunda-condicionador-300ml/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-cachos-naturais-gelatina-ativadora-fixacao-leve-450g/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-tec-oil-nutricao-profunda-mascara-capilar-250g/',
        'https://www.belezanaweb.com.br/amend-complete-repair-queratina-liquida-tratamento-reconstrutor-150ml/',
        'https://www.belezanaweb.com.br/amend-luxe-creations-extreme-repair-mascara-capilar-250g/',
        'https://www.belezanaweb.com.br/amend-luxe-creations-regenerative-care-shampoo-300ml/',
        'https://www.belezanaweb.com.br/amend-valorize-ultra-forte-spray-fixador-400ml/',
        'https://www.belezanaweb.com.br/amend-cachos-condicionador-250ml/',
        'https://www.belezanaweb.com.br/amend-marula-fabulous-nutrition-condicionador-250ml/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-egipcios-condicionador-300ml/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-indianos-condicionador-300ml/',
        'https://www.belezanaweb.com.br/amend-castanho-brilliant-realce-da-cor-condicionador-250ml/',
        'https://www.belezanaweb.com.br/amend-black-illuminated-realce-da-cor-condicionador-250ml/',
        'https://www.belezanaweb.com.br/amend-complete-repair-reconstrutor-creme-leavein-180g/',
        'https://www.belezanaweb.com.br/amend-luxe-creations-blonde-care-leavein-180g/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-egipcios-balm-selante-leavein-180g/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-indianos-balm-selante-leavein-180g/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-marroquinos-balm-selante-leavein-180g/',
        'https://www.belezanaweb.com.br/amend-cachos-mascara-capilar-250g/',
        'https://www.belezanaweb.com.br/amend-luxe-creations-blonde-care-mascara-capilar-250g/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-egipcios-mascara-capilar-300g/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-indianos-mascara-capilar-300g/',
        'https://www.belezanaweb.com.br/amend-cachos-shampoo-250ml/',
        'https://www.belezanaweb.com.br/amend-marula-fabulous-nutrition-shampoo-250ml/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-indianos-shampoo-300ml/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-egipcios-shampoo-300ml/',
        'https://www.belezanaweb.com.br/amend-black-illuminated-realce-da-cor-shampoo-250ml/',
        'https://www.belezanaweb.com.br/amend-cachos-fechados-leavein-250g/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-marroquinos-condicionador-300ml/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-marroquinos-elixir-nutritivo-oleo-capilar-75ml/',
        'https://www.belezanaweb.com.br/amend-marsala-vibrance-realce-da-cor-shampoo-250ml/',
        'https://www.belezanaweb.com.br/amend-hidratacao-mascara-capilar-250g/',
        'https://www.belezanaweb.com.br/amend-reconstrucao-mascara-capilar-250g/',
        'https://www.belezanaweb.com.br/amend-pearl-blonde-mascara-matizadora-250g/',
        'https://www.belezanaweb.com.br/amend-ice-blonde-mascara-matizadora-250g/',
        'https://www.belezanaweb.com.br/amend-gold-black-rmc-system-q-mascara-reconstrutora-300g/',
        'https://www.belezanaweb.com.br/amend-lilac-blonde-mascara-matizadora-250gr/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-gregos-shampoo-300ml/',
        'https://www.belezanaweb.com.br/amend-cachos-crespos-leavein-250g/',
        'https://www.belezanaweb.com.br/haskell-mandioca-ativador-de-cachos-240g/',
        'https://www.belezanaweb.com.br/haskell-ametista-fluido-iluminador-120ml/',
        'https://www.belezanaweb.com.br/haskell-ametista-desamarelador-condicionador-300ml/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-complexo-fortalecedor-tratamento-capilar-40ml/',
        'https://www.belezanaweb.com.br/haskell-bendito-loiro-condicionador-300ml/',
        'https://www.belezanaweb.com.br/haskell-cachos-sim-condicionador-300ml/',
        'https://www.belezanaweb.com.br/haskell-cachos-sim-condicionador-500ml/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-refil-condicionador-250ml/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-condicionador-300ml/',
        'https://www.belezanaweb.com.br/haskell-mandioca-condicionador-300ml/',
        'https://www.belezanaweb.com.br/haskell-mandioca-condicionador-500ml/',
        'https://www.belezanaweb.com.br/haskell-hidranutre-condicionador-1l/',
        'https://www.belezanaweb.com.br/haskell-hidranutre-condicionador-300ml/',
        'https://www.belezanaweb.com.br/haskell-hidranutre-condicionador-500ml/',
        'https://www.belezanaweb.com.br/haskell-jaborandi-condicionador-300ml/',
        'https://www.belezanaweb.com.br/haskell-jaborandi-condicionador-500ml/',
        'https://www.belezanaweb.com.br/haskell-murumuru-condicionador-1000ml/',
        'https://www.belezanaweb.com.br/haskell-murumuru-condicionador-300ml/',
        'https://www.belezanaweb.com.br/haskell-ora-pro-nobis-condicionador-300ml/',
        'https://www.belezanaweb.com.br/haskell-ora-pro-nobis-condicionador-500ml/',
        'https://www.belezanaweb.com.br/haskell-pos-progressiva-fluido-alinhador-120ml/',
        'https://www.belezanaweb.com.br/haskell-cachos-sim-memorizador-leave-in-300ml/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-leave-in-150g/',
        'https://www.belezanaweb.com.br/haskell-hidranutre-leavein-150g/',
        'https://www.belezanaweb.com.br/haskell-mandioca-leave-in-150g/',
        'https://www.belezanaweb.com.br/haskell-mandioca-leave-in-240g/',
        'https://www.belezanaweb.com.br/haskell-murumuru-manteiga-nutritiva-mascara-capilar-900g/',
        'https://www.belezanaweb.com.br/haskell-mandioca-mascara-de-hidratacao-500g/',
        'https://www.belezanaweb.com.br/haskell-encorpa-cabelo-mascara-engrossadora-250g/',
        'https://www.belezanaweb.com.br/haskell-murumuru-manteiga-nutritiva-mascara-capilar-500g/',
        'https://www.belezanaweb.com.br/haskell-orapronobis-mascara-capilar-300g/',
        'https://www.belezanaweb.com.br/haskell-orapronobis-mascara-capilar-500g/',
        'https://www.belezanaweb.com.br/haskell-murumuru-nectar-concentrado-35ml/',
        'https://www.belezanaweb.com.br/haskell-jaborandi-nectavita-preshampoo-35ml/',
        'https://www.belezanaweb.com.br/haskell-mandioca-nectativa-tratamento-capilar-40ml/',
        'https://www.belezanaweb.com.br/haskell-mandioca-nectavita-tratamento-capilar-35ml/',
        'https://www.belezanaweb.com.br/haskell-encorpa-cabelo-pomada-modeladora-150g/',
        'https://www.belezanaweb.com.br/haskell-bendito-loiro-proteina-capilar-150g/',
        'https://www.belezanaweb.com.br/haskell-mandioca-reparador-de-pontas-35ml/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-selante-de-pontas-serum-40ml/',
        'https://www.belezanaweb.com.br/haskell-hidranutre-serum-capilar-35ml/',
        'https://www.belezanaweb.com.br/haskell-bendito-loiro-shampoo-300ml/',
        'https://www.belezanaweb.com.br/haskell-cachos-sim-shampoo-300ml/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-refil-shampoo-250ml/',
        'https://www.belezanaweb.com.br/haskell-mandioca-shampoo-300ml/',
        'https://www.belezanaweb.com.br/haskell-mandioca-shampoo-500ml/',
        'https://www.belezanaweb.com.br/haskell-encorpa-cabelo-shampoo-500ml/',
        'https://www.belezanaweb.com.br/haskell-hidranutre-shampoo-300ml/',
        'https://www.belezanaweb.com.br/haskell-jaborandi-shampoo-300ml/',
        'https://www.belezanaweb.com.br/haskell-murumuru-shampoo-300ml/',
        'https://www.belezanaweb.com.br/haskell-ora-pro-nobis-shampoo-300ml/',
        'https://www.belezanaweb.com.br/haskell-ora-pro-nobis-shampoo-500ml/',
        'https://www.belezanaweb.com.br/haskell-pos-progressiva-condicionador-500ml/',
        'https://www.belezanaweb.com.br/haskell-cachos-sim-memorizador-leave-in-500ml/',
        'https://www.belezanaweb.com.br/haskell-ametista-mascara-desamareladora/',
        'https://www.belezanaweb.com.br/haskell-pos-progressiva-mascara-de-hidratacao-500g/',
        'https://www.belezanaweb.com.br/haskell-ametista-desamarelador-shampoo-300ml/',
        'https://www.belezanaweb.com.br/haskell-cachos-sim-shampoo-500ml/',
        'https://www.belezanaweb.com.br/haskell-pos-progressiva-shampoo-500ml/',
        'https://www.belezanaweb.com.br/widi-care-argan-oil-oleo-capilar-60ml/',
        'https://www.belezanaweb.com.br/widi-care-argan-oil-oleo-capilar-120ml/',
        'https://www.belezanaweb.com.br/widi-care-banho-de-colageno-tratamento-de-reconstrucao-intensiva-1kg/',
        'https://www.belezanaweb.com.br/widi-care-banho-de-colageno-mascara-de-reconstrucao-280ml/',
        'https://www.belezanaweb.com.br/widi-care-cabeleira-crescimento-e-fortalecimento-fluido-fortificante-120ml/',
        'https://www.belezanaweb.com.br/widi-care-coconut-oil-1kg-mascara-nutritiva-1kg/',
        'https://www.belezanaweb.com.br/widi-care-coconut-oil-oleo-hidratante-capilar-120ml/',
        'https://www.belezanaweb.com.br/widi-care-curvas-magicas-creme-de-pentear-300ml/',
        'https://www.belezanaweb.com.br/widi-care-encaracolando-a-juba-creme-de-pentear-1l/',
        'https://www.belezanaweb.com.br/widi-care-encrespando-a-juba-creme-de-pentear-1l/',
        'https://www.belezanaweb.com.br/widi-care-encrespando-a-juba-creme-de-pentear-500ml/',
        'https://www.belezanaweb.com.br/widi-care-higienizando-a-juba-shampoo-1l/',
        'https://www.belezanaweb.com.br/widi-care-infusao-20-tratamento-acidificante-1kg/',
        'https://www.belezanaweb.com.br/widi-care-infusao-20-tratamento-acidificante-300g/',
        'https://www.belezanaweb.com.br/widi-care-blend-de-oleos-vegetais-tratamento-capilar-60ml/',
        'https://www.belezanaweb.com.br/widi-care-juba-co-wash-condicionador-500ml/',
        'https://www.belezanaweb.com.br/widi-care-juba-hidronutritiva-mascara-capilar-500g/',
        'https://www.belezanaweb.com.br/widi-care-liso-maravilha-condicionador-300ml/',
        'https://www.belezanaweb.com.br/widi-care-liso-maravilha-protetor-termico-200ml/',
        'https://www.belezanaweb.com.br/widi-care-liso-maravilha-mascara-capilar-300g/',
        'https://www.belezanaweb.com.br/widi-care-liso-maravilha-shampoo-300ml/',
        'https://www.belezanaweb.com.br/widi-care-liso-maravilha-serum-capilar-60ml/',
        'https://www.belezanaweb.com.br/widi-care-magic-treatment-moroccan-oil-leavein-60ml/',
        'https://www.belezanaweb.com.br/widi-care-modelando-a-juba-geleia-seladora-300g/',
        'https://www.belezanaweb.com.br/widi-care-operacao-resgate-mascara-reconstrucao-1l/',
        'https://www.belezanaweb.com.br/widi-care-operacao-resgate-mascara-reconstrucao-300ml/',
        'https://www.belezanaweb.com.br/widi-care-perolas-de-caviar-shampoo-antiresiduos-300ml/',
        'https://www.belezanaweb.com.br/widi-care-perolas-de-caviar-condicionador-hidratante-300ml/',
        'https://www.belezanaweb.com.br/widi-care-perolas-de-caviar-shampoo-hidratante-300ml/',
        'https://www.belezanaweb.com.br/widi-care-phytomanga-finalizador-multifuncional-300ml/',
        'https://www.belezanaweb.com.br/widi-care-phyto-manga-mascara-capilar-300g/',
        'https://www.belezanaweb.com.br/widi-care-phytomanga-mascara-capilar-500g/',
        'https://www.belezanaweb.com.br/widi-care-phytomanga-shampoo-300ml/',
        'https://www.belezanaweb.com.br/widi-care-sete-oleos-condicionador-300ml/',
        'https://www.belezanaweb.com.br/widi-care-sete-oleos-mascara-nutritiva-500g/',
        'https://www.belezanaweb.com.br/widi-care-sou-10-leavein-200ml/',
        'https://www.belezanaweb.com.br/haskell-jaborandi-tonico-fortalecedor-120ml/',
        'https://www.belezanaweb.com.br/haskell-bendito-loiros-shampoo-500ml/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-shampoo-300ml/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-shampoo-500ml/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-shampoo-1l/',
        'https://www.belezanaweb.com.br/haskell-murumuru-manteiga-nutritiva-300g/',
        'https://www.belezanaweb.com.br/haskell-bendito-loiro-mascara-capilar-300g/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-mascara-capilar-300g/',
        'https://www.belezanaweb.com.br/haskell-murumuru-manteiga-hidratante-mascara-capilar-250g/',
        'https://www.belezanaweb.com.br/haskell-cavalo-forte-complexo-fortalecedor-35ml/',
        'https://www.belezanaweb.com.br/brae-glow-shine-shampoo-250ml/',
        'https://www.belezanaweb.com.br/brae-glow-shine-condicionador-250ml/',
        'https://www.belezanaweb.com.br/brae-glow-shine-mascara-capilar-200g/',
        'https://www.belezanaweb.com.br/brae-glow-shine-fluido-ativador-de-brilho-200ml/',
        'https://www.belezanaweb.com.br/brae-defense-anti-hair-loss-shampoo-250ml/',
        'https://www.belezanaweb.com.br/brae-defense-antiqueda-condicionador-250ml/',
        'https://www.belezanaweb.com.br/brae-defense-suplemento-alimentar-30-capsulas/',
        'https://www.belezanaweb.com.br/brae-defense-antiqueda-tonico-capilar-60ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-nutrienrich-mascara-de-nutricao-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-blonde-recharge-shampoo-desamarelador-1000ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-volume-boost-shampoo-250ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-volume-boost-crystal-mascara-capilar-500ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-volume-boost-shampoo-1-litro/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-balance-acqua-pure-shampoo-antirresiduos-1000ml/',
        'https://www.belezanaweb.com.br/wella-professionals-elements-renewing-shampoo-1l/',
        'https://www.belezanaweb.com.br/wella-professionals-renewing-elements-shampoo-250ml/',
        'https://www.belezanaweb.com.br/wella-professionals-elements-renewing-mascara-capilar-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-nutricurls-shampoo-250ml/',
        'https://www.belezanaweb.com.br/wella-professionals-nutricurls-shampoo-1-litro/',
        'https://www.belezanaweb.com.br/wella-professionals-nutricurls-condicionador-200ml/',
        'https://www.belezanaweb.com.br/wella-professionals-nutricurls-condicionador-1-litro/',
        'https://www.belezanaweb.com.br/wella-profissionals-nutricurls-condicionador-cowash-250ml/',
        'https://www.belezanaweb.com.br/wella-professionals-nutricurls-mascara-de-nutricao-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-nutricurls-mascara-de-nutricao-500ml/',
        'https://www.belezanaweb.com.br/wella-professionals-nutricurls-curlixir-leavein-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-color-motion-shampoo-1l/',
        'https://www.belezanaweb.com.br/wella-professionals-color-motion-condicionador-1000ml/',
        'https://www.belezanaweb.com.br/wella-professionals-color-motion-mascara-capilar-500ml/',
        'https://www.belezanaweb.com.br/wella-professionals-color-motion-shampoo-250ml/',
        'https://www.belezanaweb.com.br/wella-professionals-color-motion-condicionador-200ml/',
        'https://www.belezanaweb.com.br/wella-color-motion-precolor-treatment-mascara-de-tratamento-capilar-185ml/',
        'https://www.belezanaweb.com.br/sp-system-professional-luxe-oil-keratin-protect-shampoo-1l/',
        'https://www.belezanaweb.com.br/sp-system-professional-luxe-oil-keratin-protect-shampoo-200ml/',
        'https://www.belezanaweb.com.br/sp-system-professional-luxe-oil-keratin-restore-mascara-capilar-150ml/',
        'https://www.belezanaweb.com.br/sp-system-professional-luxe-oil-oleo-capilar-100ml/',
        'https://www.belezanaweb.com.br/sp-system-professional-liquid-hair-tratamento-100ml/',
        'https://www.belezanaweb.com.br/amend-luxe-creations-extreme-repair-condicionador-250ml/',
        'https://www.belezanaweb.com.br/amend-regenerative-care-luxe-creations-condicionador-300ml/',
        'https://www.belezanaweb.com.br/amend-expertise-liso-descomplicado-condicionador-250ml/',
        'https://www.belezanaweb.com.br/amend-luxe-creations-regenerative-care-mascara-capilar-250g/',
        'https://www.belezanaweb.com.br/amend-luxe-creations-extreme-repair-shampoo-250ml/',
        'https://www.belezanaweb.com.br/amend-expertise-liso-descomplicado-shampoo-250ml/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-gregos-balm-selante-capilar-180g/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-gregos-condicionador-restaurador-300ml/',
        'https://www.belezanaweb.com.br/amend-gold-black-nutritivo-creme-leavein-250g/',
        'https://www.belezanaweb.com.br/amend-millenar-oleos-gregos-mascara-capilar-300ml/',
        'https://www.belezanaweb.com.br/amend-gold-black-nutritivo-ultra-reparador-de-pontas-30ml/',
        'https://www.belezanaweb.com.br/amend-complete-repair-shampoo-250ml/',
        'https://www.belezanaweb.com.br/amend-specialist-blonde-mascara-matizadora-300g/',
        'https://www.belezanaweb.com.br/amend-luxe-creations-extreme-repair-overnight-leavein-reconstrutor-capilar-180ml/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-cachos-naturais-ondulados-e-cacheados-ativador-de-cachos-300ml/',
        'https://www.belezanaweb.com.br/tigi-bed-head-small-talk-leavein-240ml/',
        'https://www.belezanaweb.com.br/brae-divine-plume-sensation-serum-reparador-capilar-60ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-color-brilliance-spray-miracle-bb-leavein-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-nutrienrich-wonder-balm-levein-150ml/',
        'https://www.belezanaweb.com.br/sp-system-professional-luxe-oil-oleo-capilar-30ml/',
        'https://www.belezanaweb.com.br/brae-essential-condicionador-1l/',
        'https://www.belezanaweb.com.br/brae-essential-mascara-200g/',
        'https://www.belezanaweb.com.br/brae-glow-shine-condicionador-1l/',
        'https://www.belezanaweb.com.br/brae-glow-shine-mascara-capilar-500g/',
        'https://www.belezanaweb.com.br/bruna-tavares-bt-jelly-sabrina-gloss-labial-35ml/',
        'https://www.belezanaweb.com.br/bruna-tavares-bt-jelly-tint-gloss-labial-35ml/',
        'https://www.belezanaweb.com.br/bruna-tavares-bt-light-golden-po-iluminador-compacto-5g/',
        'https://www.belezanaweb.com.br/bruna-tavares-bt-jelly-peach-gloss-labial-35ml/',
        'https://www.belezanaweb.com.br/bruna-tavares-bt-multicover-t20-corretivo-liquido-8g/',
        'https://www.belezanaweb.com.br/wella-professionals-oil-reflections-oleo-capilar-30ml/',
        'https://www.belezanaweb.com.br/amend-complete-repair-condicionador-250ml/',
        'https://www.belezanaweb.com.br/amend-25-anos-reparador-de-pontas-55ml-divdiv/',
        'https://www.belezanaweb.com.br/bruna-tavares-bt-skin-d20-base-liquida-40ml/',
        'https://www.belezanaweb.com.br/wella-professionals-elements-lightweight-renewing-condicionador-1l/',
        'https://www.belezanaweb.com.br/wella-professionals-elements-renewing-mask-mascara-de-tratamento-500ml/',
        'https://www.belezanaweb.com.br/wella-professionals-oil-reflections-luminous-instant-condicionador-200ml/',
        'https://www.belezanaweb.com.br/wella-professionals-fusion-shampoo-250ml/',
        'https://www.belezanaweb.com.br/amend-marula-fabulous-nutrition-oleo-capilar-60ml/',
        'https://www.belezanaweb.com.br/wella-professionals-oil-reflections-luminous-reveal-shampoo-1-litro/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-hidratacao-intensiva-condicionador-300ml/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-hidratacao-intensiva-oleo-capilar-60ml/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-hidratacao-intensiva-leavein-200ml/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-hidratacao-intensiva-mascara-capilar-250g/',
        'https://www.belezanaweb.com.br/widi-care-curvas-magicas-mascara-capilar-300ml/',
        'https://www.belezanaweb.com.br/haskell-supermascara-brilho-espelhado-tratamento-capilar-240g/',
        'https://www.belezanaweb.com.br/wella-professionals-fusion-condicionador-1-litro/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-nutrienrich-frizz-control-leavein-antifrizz-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-color-brilliance-mascara-capilar-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-elements-renewing-mask-mascara-de-tratamento-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-elements-conditioning-spray-leave-in-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-oil-reflections-luminous-reveal-shampoo-250ml/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-sun-condicionador-200ml/',
        'https://www.belezanaweb.com.br/wella-professionals-blondor-multi-blonde-po-descolorante-800g/',
        'https://www.belezanaweb.com.br/wella-professionals-invigo-sun-leavein-150ml/',
        'https://www.belezanaweb.com.br/wella-professionals-eimi-shape-control-mousse-300ml/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-cachinhos-naturais-crespos-ativador-de-cachos-300ml/',
        'https://www.belezanaweb.com.br/arvensis-cosmeticos-naturais-cachos-naturais-spray-day-after-spray-ativador-de-cachos-250ml/',
        'https://www.belezanaweb.com.br/revlon-uniq-one-leavein-150ml/',
        'https://www.belezanaweb.com.br/brae-divine-shampoo-250ml/',
        'https://www.belezanaweb.com.br/brae-divine-condicionador-250ml/',
        'https://www.belezanaweb.com.br/brae-divine-home-care-mascara-capilar-200g/',
        'https://www.belezanaweb.com.br/brae-revival-shampoo-250ml/',
        'https://www.belezanaweb.com.br/brae-revival-condicionador-250ml/',
        'https://www.belezanaweb.com.br/brae-revival-mascara-de-reconstrucao-200g/',
        'https://www.belezanaweb.com.br/brae-soul-color-condicionador-250ml/',
        'https://www.belezanaweb.com.br/brae-soul-color-shampoo-250ml/',
        'https://www.belezanaweb.com.br/brae-soul-color-mascara-capilar-200g/',
        'https://www.belezanaweb.com.br/brae-bond-angel-plex-effect-n3-bond-fortifier-tratamento-fortificante-100g/',
        'https://www.belezanaweb.com.br/brae-bond-angel-plex-effect-n1-bond-maker-tratamento-protetor-500ml/',
        'https://www.belezanaweb.com.br/brae-bond-angel-plex-effect-n2-bond-reconstructor-tratamento-reconstrutor-500ml/',
        'https://www.belezanaweb.com.br/brae-divine-antifrizz-shampoo-1000ml/',
        'https://www.belezanaweb.com.br/brae-divine-antifrizz-condicionador-1l/',
        'https://www.belezanaweb.com.br/brae-divine-mascara-capilar-500g/',
        'https://www.belezanaweb.com.br/brae-divine-mascara-capilar-60ml/',
        'https://www.belezanaweb.com.br/brae-bond-angel-shampoo-matizador-1000ml/',
        'https://www.belezanaweb.com.br/brae-bond-angel-ph-acidificante-matizador-1000ml/',
        'https://www.belezanaweb.com.br/brae-bond-angel-shampoo-matizador-250ml/',
        'https://www.belezanaweb.com.br/brae-bond-angel-ph-acidificante-matizador-250ml/',
        'https://www.belezanaweb.com.br/brae-bond-angel-thermal-blond-leavein-matizador-200ml/',
        'https://www.belezanaweb.com.br/brae-revival-one-tratamento-reconstrutor-1000ml/',
        'https://www.belezanaweb.com.br/brae-revival-two-repositor-de-massa-tratamento-reconstrutor-1000ml/',
        'https://www.belezanaweb.com.br/brae-revival-condicionador-1l/',
        'https://www.belezanaweb.com.br/brae-revival-mascara-de-reconstrucao-500g/',
        'https://www.belezanaweb.com.br/brae-revival-intense-shine-moisturizing-spray-leavein-150ml/',
        'https://www.belezanaweb.com.br/brae-revival-leavein-200ml/',
        'https://www.belezanaweb.com.br/brae-gorgeous-volume-shampoo-1000ml/',
        'https://www.belezanaweb.com.br/brae-gorgeous-volume-condicionador-1000ml/',
        'https://www.belezanaweb.com.br/brae-gorgeous-volume-shampoo-250ml/',
        'https://www.belezanaweb.com.br/brae-gorgeous-volume-condicionador-250ml/',
        'https://www.belezanaweb.com.br/widi-care-encrespando-a-juba-creme-de-pentear-500ml/',
        'https://www.belezanaweb.com.br/widi-care-super-poderosas-shampoo-300ml/',
        'https://www.belezanaweb.com.br/brae-gorgeous-volume-condicionador-250ml/',
    ]
    try:
        asyncio.run(process_urls(beleza_na_web_urls))
    except Exception as e:
        logging.error(f'Erro ao executar o crawler: {e}')
        raise
