import asyncio
import json
import os
import re
import time
from datetime import datetime
from pprint import pprint

import aiohttp
from crawl4ai import AsyncWebCrawler
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright



async def scrape_epoca_cosmeticos(url):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(url)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(3000)

        # Extrair SKU da URL
        sku = None
        try:
            match = re.search(r'q=([\d]+)', url)
            sku = match.group(1) if match else None
        except Exception as e:
            print(f"Erro ao extrair SKU: {e}")
        if not sku:
            print(f'SKU não encontrado na URL: {url}')
            return []

        products = await page.query_selector_all('div[data-testid="productItemComponent"]')
        lojas = []

        for idx, product in enumerate(products):
            try:
                # Nome do produto
                nome = await product.query_selector('.name')
                nome = await nome.inner_text() if nome else ""
                nome = nome.strip()
                
                # Preço (pega o preço à vista, se disponível)
                preco_el = await product.query_selector('.product-price_spotPrice__k_4YC')
                if not preco_el:
                    preco_el = await product.query_selector('.product-price_priceList__uepac')
                preco = await preco_el.inner_text() if preco_el else ""
                preco_final_str = re.sub(r"[^\d,]", "", preco).replace(",", ".")
                preco_final = float(preco_final_str) if preco_final_str else 0.0
                
                # Review (pega o número entre parênteses)
                review = 4.5  # Valor padrão, como na Beleza na Web
                review_el = await product.query_selector('.rate p')
                if review_el:
                    review_text = await review_el.inner_text()
                    review_text = review_text.strip()
                    match = re.search(r"\(([0-9.,]+)\)", review_text)
                    if match:
                        review = float(match.group(1).replace(",", "."))
                
                # Imagem
                img_el = await product.query_selector("img")
                imagem = await img_el.get_attribute("src") if img_el else ""
                if imagem and imagem.startswith("//"):
                    imagem = f"https:{imagem}"
                
                # Link
                link_el = await product.query_selector('a[data-content-item="true"]')
                link = await link_el.get_attribute("href") if link_el else ""
                if link and not link.startswith("http"):
                    link = "https://www.epocacosmeticos.com.br" + link

                # Abre nova aba para detalhes
                detail_page = await context.new_page()
                await detail_page.goto(link)
                await detail_page.wait_for_load_state("domcontentloaded")
                await detail_page.wait_for_timeout(1500)
                
                # Descrição (curta)
                descricao = ""
                desc_el = await detail_page.query_selector('p[data-product-title="true"]')
                if desc_el:
                    descricao = await desc_el.inner_text()
                    descricao = descricao.strip()
                else:
                    meta_desc = await detail_page.query_selector('meta[name="description"]')
                    if meta_desc:
                        descricao = await meta_desc.get_attribute("content")
                
                # Nome da loja (quem vende e entrega)
                loja = "Época Cosméticos"
                loja_el = await detail_page.query_selector('.pdp-buybox-seller_sellerInfo__BmOa4 a span')
                if loja_el:
                    loja = await loja_el.inner_text()
                    loja = loja.strip()
                
                await detail_page.close()

                data_hora = datetime.utcnow().isoformat() + "Z"
                status = "ativo"
                marketplace = "Época Cosméticos"
                key_loja = loja.lower().replace(" ", "")
                key_sku = f"{key_loja}_{sku}" if sku else None

                result = {
                    "sku": sku if sku else "SKU não encontrado",
                    "loja": loja,
                    "preco_final": preco_final,
                    "data_hora": data_hora,
                    "marketplace": marketplace,
                    "key_loja": key_loja,
                    "key_sku": key_sku,
                    "descricao": descricao,
                    "review": review,
                    "imagem": imagem,
                    "status": status
                }
                lojas.append(result)
            except Exception as e:
                print(f"Erro ao processar produto {idx}: {e}")

        await context.close()
        await browser.close()
        return lojas                

async def extract_data_from_amazon(target_url: str) -> list:
    """
    Extrai dados de vendedores de uma página de produto da Amazon, incluindo vendedor principal
    e outras ofertas, usando Playwright. Retorna uma lista de dicionários com os dados formatados.

    Args:
        target_url: URL da página de produto da Amazon.

    Returns:
        list: Lista de dicionários com dados dos vendedores.
    """
    start_time = time.time()
    lojas = []
    storage_file = "amz_auth.json"

    # Verificar se o arquivo de autenticação existe
    if not os.path.exists(storage_file):
        print(f"Erro: Arquivo de autenticação {storage_file} não encontrado.")
        return lojas

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Carregar cookies
            try:
                with open(storage_file, 'r') as f:
                    auth_data = json.load(f)
                    await context.add_cookies(auth_data.get('cookies', []))
                print(f"After loading cookies: {time.time() - start_time:.2f} seconds")
            except Exception as e:
                print(f"Erro ao carregar cookies: {e}")
                return lojas

            # Navegar para a URL
            print(f"Navegando para {target_url}")
            response = await page.goto(target_url, timeout=30000)
            if response and response.status != 200:
                print(f"Falha ao carregar página {target_url}. Status: {response.status}")
                return lojas
            await page.wait_for_load_state('domcontentloaded', timeout=15000)
            print(f"After navigation: {time.time() - start_time:.2f} seconds")

            # Extrair SKU
            sku = "SKU não encontrado"
            try:
                match = re.search(r'/dp/([A-Z0-9]{10})', target_url)
                if match:
                    sku = match.group(1)
            except Exception as e:
                print(f"Erro ao extrair SKU: {e}")

            # Funções para extração concorrente
            async def get_description():
                try:
                    await page.wait_for_selector('#productTitle', timeout=7000)
                    return (await page.locator('#productTitle').first.inner_text()).strip()
                except Exception as e:
                    print(f"Erro ao extrair descrição: {e}")
                    return "Descrição não encontrada"

            async def get_image():
                try:
                    await page.wait_for_selector('#landingImage', timeout=7000)
                    return await page.locator('#landingImage').first.get_attribute('src')
                except Exception as e:
                    print(f"Erro ao extrair imagem: {e}")
                    return "Imagem não encontrada"

            async def get_review():
                try:
                    review_span = page.locator('a.a-popover-trigger span[aria-hidden="true"]').first
                    review_text = (await review_span.inner_text(timeout=7000)).strip()
                    print(f"Texto da review capturado: '{review_text}'")
                    if review_text and re.match(r'^\d+\.\d$', review_text.replace(',', '.')):
                        return float(review_text.replace(',', '.'))
                    print("Review não encontrada ou inválida, usando padrão 4.5")
                    return 4.5
                except Exception as e:
                    print(f"Erro ao extrair review: {e}")
                    return 4.5

            # Executar extração concorrente
            descricao, imagem, review = await asyncio.gather(
                get_description(),
                get_image(),
                get_review()
            )
            print(f"After element extraction: {time.time() - start_time:.2f} seconds")

            # Extrair vendedor principal e preço
            seller_name = "Não informado"
            preco_final = 0.0
            try:
                seller = page.locator("#sellerProfileTriggerId").first
                seller_name = (await seller.inner_text(timeout=7000)).strip()
                seller_name = re.sub(r'Vendido por\s*', '', seller_name).strip()

                price_span = page.locator('div.a-section.a-spacing-micro span.a-offscreen').first
                price_text = re.sub(r'[^\d,.]', '', (await price_span.inner_text(timeout=7000)).strip()).replace(',', '.')
                if re.match(r'^\d+\.\d+$', price_text):
                    preco_final = float(price_text)
                else:
                    print(f"Preço inválido na página principal: {price_text}")

                if seller_name != "Não informado" and preco_final > 0.0:
                    key_loja = seller_name.lower().replace(' ', '')
                    key_sku = f"{key_loja}_{sku}" if sku != "SKU não encontrado" else f"{key_loja}_sem_sku"
                    lojas.append({
                        'sku': sku,
                        'loja': seller_name,
                        'preco_final': preco_final,
                        'data_hora': datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
                        'marketplace': 'Amazon',
                        'key_loja': key_loja,
                        'key_sku': key_sku,
                        'descricao': descricao,
                        'review': review,
                        'imagem': imagem,
                        'status': 'ativo'
                    })
                    print(f"Vendedor principal capturado: {seller_name}, Preço: {preco_final}")
            except Exception as e:
                print(f"Erro ao extrair vendedor/preço da página principal: {e}")

            # Acessar página de ofertas
            try:
                compare_button = page.get_by_role("button", name=re.compile("Comparar outras.*ofertas|Ver todas as ofertas"))
                await compare_button.wait_for(state='visible', timeout=10000)
                print("Botão de comparação encontrado")
                await compare_button.click(timeout=10000)
                print(f"After clicking compare button: {time.time() - start_time:.2f} seconds")

                details_link = page.get_by_role("link", name="Ver mais detalhes sobre esta")
                await details_link.wait_for(state='visible', timeout=10000)
                print("Link 'Ver mais detalhes' encontrado")
                await details_link.click(timeout=10000)
                print(f"After clicking details link: {time.time() - start_time:.2f} seconds")

                await page.wait_for_load_state('domcontentloaded', timeout=15000)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
                print(f"After loading offers page: {time.time() - start_time:.2f} seconds")
            except Exception as e:
                print(f"Erro ao acessar página de ofertas: {e}")
                print("Page content for debugging:", await page.content()[:1000])
                return lojas

            # Extrair ofertas
            try:
                await page.wait_for_selector("#aod-offer", timeout=10000)
                offer_elements = await page.locator("#aod-offer").all()
                print(f"Encontradas {len(offer_elements)} ofertas")
                for i, offer in enumerate(offer_elements, 1):
                    try:
                        preco_final = 0.0
                        try:
                            price_span = offer.locator('span.aok-offscreen').first
                            price_text = re.sub(r'[^\d,.]', '', (await price_span.inner_text(timeout=5000)).strip()).replace(',', '.')
                            if re.match(r'^\d+\.\d+$', price_text):
                                preco_final = float(price_text)
                            else:
                                print(f"Preço inválido na oferta {i}: {price_text}")
                        except Exception:
                            try:
                                price_whole = (await offer.locator("span.a-price-whole").first.inner_text(timeout=5000)).strip()
                                price_fraction = (await offer.locator("span.a-price-fraction").first.inner_text(timeout=5000)).strip()
                                price_text = f"{re.sub(r'[^\d]', '', price_whole)}.{price_fraction}"
                                if re.match(r'^\d+\.\d+$', price_text):
                                    preco_final = float(price_text)
                                else:
                                    print(f"Preço inválido na oferta {i} (fallback): {price_text}")
                            except Exception as e:
                                print(f"Erro ao extrair preço na oferta {i}: {e}")
                                continue

                        seller_name = "Não informado"
                        try:
                            seller = offer.locator("a.a-size-small.a-link-normal").first
                            seller_name = (await seller.inner_text(timeout=5000)).strip()
                            seller_name = re.sub(r'Vendido por\s*', '', seller_name).strip()
                        except Exception as e:
                            print(f"Erro ao extrair vendedor na oferta {i}: {e}")
                            continue

                        if any(s['loja'] == seller_name for s in lojas):
                            print(f"Vendedor {seller_name} já capturado, ignorando duplicata")
                            continue

                        key_loja = seller_name.lower().replace(' ', '')
                        key_sku = f"{key_loja}_{sku}" if sku != "SKU não encontrado" else f"{key_loja}_sem_sku"
                        lojas.append({
                            'sku': sku,
                            'loja': seller_name,
                            'preco_final': preco_final,
                            'data_hora': datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
                            'marketplace': 'Amazon',
                            'key_loja': key_loja,
                            'key_sku': key_sku,
                            'descricao': descricao,
                            'review': review,
                            'imagem': imagem,
                            'status': 'ativo'
                        })
                        print(f"Oferta {i} capturada: {seller_name}, Preço: {preco_final}")
                    except Exception as e:
                        print(f"Erro ao processar oferta {i}: {e}")
                        continue
            except Exception as e:
                print(f"Erro ao extrair ofertas: {e}")
                print("Page content for debugging:", await page.content()[:1000])

        finally:
            await context.storage_state(path="amz_auth.json")
            await context.close()
            await browser.close()

    # Calcular e exibir tempo de execução
    end_time = time.time()
    execution_time = end_time - start_time
    print(f"Execution time: {execution_time:.2f} seconds")
    return lojas

def extract_data_from_markdown_beleza(markdown):
    """Extrai SKU, descrição, review, imagem e dados de lojas do Markdown (Beleza na Web)."""
    lojas = []

    # Extrai SKU
    sku_pattern = r'\*\*Cod:\*\* (MP\d+|\d+)'
    sku_match = re.search(sku_pattern, markdown)
    sku = sku_match.group(1) if sku_match else None
    if not sku:
        print('SKU não encontrado no Markdown (Beleza na Web)')
        return []

    # Extrai descrição
    desc_pattern = r'\[Voltar para a página do produto\]\(https://www\.belezanaweb\.com\.br/(.+?)\)'
    desc_match = re.search(desc_pattern, markdown)
    if desc_match:
        url_text = desc_match.group(1)
        descricao = ' '.join(word.capitalize() for word in url_text.split('-'))
        descricao = descricao.replace('Condicionador ', 'Condicionador - ')
    else:
        descricao = 'Descrição não encontrada'
    print(f'Descrição capturada (Beleza na Web): {descricao!r}')

    # Extrai review
    review_pattern = r'Review[:\s]*(\d+[\.,]\d+|\d+)'
    review_match = re.search(review_pattern, markdown)
    review = (
        float(review_match.group(1).replace(',', '.')) if review_match else 4.5
    )

    # Extrai imagem
    img_pattern_with_desc = r'!\[.*?\]\((https://res\.cloudinary\.com/beleza-na-web/image/upload/.*?/v1/imagens/product/.*?/.*?\.(?:png|jpg))\)'
    img_match_with_desc = re.search(img_pattern_with_desc, markdown)
    imagem = (
        img_match_with_desc.group(1)
        if img_match_with_desc
        else 'Imagem não encontrada'
    )
    if imagem == 'Imagem não encontrada':
        img_pattern_empty = r'!\[\]\((https?://[^\s)]+)\)'
        img_matches_empty = re.findall(img_pattern_empty, markdown)
        imagem = (
            img_matches_empty[0]
            if img_matches_empty
            else 'Imagem não encontrada'
        )

    # Extrai lojas e preços
    loja_pattern = r'Vendido por \*\*(.*?)\*\* Entregue por Beleza na Web'
    preco_com_desconto_pattern = r'-[\d]+%.*?\nR\$ ([\d,\.]+)'
    preco_venda_pattern = r'(?<!De )R\$ ([\d,\.]+)(?!\s*3x)'
    blocos = re.split(
        r'(?=Vendido por \*\*.*?\*\* Entregue por Beleza na Web)', markdown
    )
    for bloco in blocos:
        if 'Vendido por' not in bloco:
            continue
        loja_match = re.search(loja_pattern, bloco)
        preco_com_desconto_match = re.search(preco_com_desconto_pattern, bloco)
        preco_venda_match = re.search(preco_venda_pattern, bloco)
        nome_loja = loja_match.group(1) if loja_match else 'Beleza na Web'
        if preco_com_desconto_match:
            preco_final_str = preco_com_desconto_match.group(1)
            preco_final_str = preco_final_str.replace('.', '').replace(
                ',', '.'
            )
            preco_final = float(preco_final_str)
        elif preco_venda_match:
            preco_final_str = preco_venda_match.group(1)
            preco_final_str = preco_final_str.replace('.', '').replace(
                ',', '.'
            )
            preco_final = float(preco_final_str)
        else:
            preco_final = 0.0
        key_loja = nome_loja.lower().replace(' ', '')
        loja = {
            'sku': sku,
            'loja': nome_loja,
            'preco_final': preco_final,
            'data_hora': datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'marketplace': 'Beleza na Web',
            'key_loja': key_loja,
            'key_sku': f'{key_loja}_{sku}',
            'descricao': descricao,
            'review': review,
            'imagem': imagem,
            'status': 'ativo',
        }
        lojas.append(loja)

    return lojas

async def extract_data_from_meli(url: str) -> list:
    """
    Extrai dados de produtos do Mercado Livre e retorna uma lista de vendedores usando Playwright Async API.
    
    Args:
        url: URL da página do produto
        
    Returns:
        list: Lista de dicionários com dados dos vendedores, formatada como Beleza na Web
    """
    # Record start time
    start_time = time.time()
    
    lojas = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            # Configure context with minimal settings for speed
            context = await browser.new_context(
                storage_state="meli_auth.json",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720}
            )
            try:
                page = await context.new_page()
                
                # Block images and media to speed up page load
                await context.route("**/*.{png,jpg,jpeg,webp,gif,mp4,webm}", lambda route: route.abort())
                
                # Navigate to the URL
                response = await page.goto(url, timeout=30000)  # 30-second timeout
                print(f"After navigation: {time.time() - start_time:.2f} seconds")
                if response.status != 200:
                    print(f"Failed to load page {url}. Status code: {response.status}")
                    return lojas
                
                # Extract SKU from URL (fast regex operation)
                sku = None
                try:
                    match = re.search(r'(?:/p/|item_id%3A)(MLB\d+)', url)
                    sku = match.group(1) if match else None
                    if not sku:
                        print(f"SKU not found in URL: {url}")
                except Exception as e:
                    print(f"Error extracting SKU: {e}")
                
                # Parallelize extraction of description, image, and review
                async def get_description():
                    try:
                        await page.wait_for_selector('h1.ui-pdp-title', timeout=7000)
                        return await page.locator('h1.ui-pdp-title').inner_text()
                    except Exception as e:
                        print(f"Error extracting description: {e}")
                        return "Descrição não encontrada"
                
                async def get_image():
                    try:
                        await page.wait_for_selector('img.ui-pdp-image', timeout=7000)
                        return await page.locator('img.ui-pdp-image').first.get_attribute('src')
                    except Exception as e:
                        print(f"Error extracting image: {e}")
                        return "Imagem não encontrada"
                
                async def get_review():
                    try:
                        await page.wait_for_selector('.ui-pdp-reviews__rating__summary__average', timeout=7000)
                        review_text = await page.locator('.ui-pdp-reviews__rating__summary__average').inner_text()
                        review_match = re.search(r'(\d+\.\d+)', review_text)
                        return float(review_match.group(1)) if review_match else 4.5
                    except Exception as e:
                        print(f"Error extracting review: {e}")
                        return 4.5
                
                # Run extraction tasks concurrently
                try:
                    descricao, imagem, review = await asyncio.gather(
                        get_description(),
                        get_image(),
                        get_review()
                    )
                    print(f"After element extraction: {time.time() - start_time:.2f} seconds")
                except Exception as e:
                    print(f"Error during concurrent element extraction: {e}")
                    descricao, imagem, review = "Descrição não encontrada", "Imagem não encontrada", 4.5
                
                # Extract seller data from melidata
                try:
                    script_content = await page.evaluate(
                        """() => {
                            const scripts = document.querySelectorAll('script');
                            for (let script of scripts) {
                                if (script.textContent.includes('melidata("add", "event_data"')) {
                                    return script.textContent;
                                }
                            }
                            return null;
                        }"""
                    )
                    
                    if script_content:
                        pattern = r'melidata\("add", "event_data", ({.*?})\);'
                        match = re.search(pattern, script_content, re.DOTALL)
                        if match:
                            event_data = json.loads(match.group(1))
                            items = event_data.get('items', [])
                            
                            for item in items:
                                nome_loja = item.get('seller_name', 'Mercado Livre')
                                key_loja = nome_loja.lower().replace(' ', '')
                                
                                seller = {
                                    'sku': sku if sku else 'SKU não encontrado',
                                    'loja': nome_loja,
                                    'preco_final': float(item.get('price', 0.0)),
                                    'data_hora': datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
                                    'marketplace': 'Mercado Livre',
                                    'key_loja': key_loja,
                                    'key_sku': f'{key_loja}_{sku}' if key_loja and sku else None,
                                    'descricao': descricao,
                                    'review': review,
                                    'imagem': imagem,
                                    'status': 'ativo'
                                }
                                lojas.append(seller)
                        else:
                            print("Melidata event_data not found in script content")
                    else:
                        print("No melidata script found")
                    print(f"After melidata extraction: {time.time() - start_time:.2f} seconds")
                except json.JSONDecodeError as e:
                    print(f"Error parsing melidata JSON: {e}")
                except Exception as e:
                    print(f"Error extracting melidata: {e}")
                
                # Save session state
                try:
                    await context.storage_state(path='meli_auth.json')
                except Exception as e:
                    print(f"Error saving storage state: {e}")
                    
            except Exception as e:
                print(f"Error processing page {url}: {e}")
            finally:
                await context.close()
        except FileNotFoundError:
            print("Error: meli_auth.json file not found. Please ensure it exists in the script's directory.")
        except json.JSONDecodeError:
            print("Error: meli_auth.json is invalid or corrupted. Please verify its contents.")
        except Exception as e:
            print(f"Error setting up context: {e}")
        finally:
            await browser.close()
    
    # Calculate and print execution time
    end_time = time.time()
    execution_time = end_time - start_time
    print(f"Execution time: {execution_time:.2f} seconds")
    
    return lojas

async def crawl_url(crawler, url, max_retries=3):
    """Extrai dados de uma URL usando Crawl4AI ou Playwright (para Mercado Livre e Amazon) com re-tentativas."""
    for attempt in range(max_retries):
        try:
            print(f'Extraindo dados da URL: {url} (Tentativa {attempt + 1}/{max_retries})')
            if 'mercadolivre' in url.lower():
                lojas = await extract_data_from_meli(url)
            elif 'amazon' in url.lower():
                lojas = await extract_data_from_amazon(url)
            elif 'epoca' in url.lower():
                lojas = await scrape_epoca_cosmeticos(url)  # Usa await em vez de asyncio.run
            elif 'belezanaweb' in url.lower():
                result = await crawler.arun(
                    url=url,
                    timeout=180,
                    js_enabled=True,
                    bypass_cache=True,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    },
                )
                markdown_content = result.markdown
                print('Markdown gerado:')
                lojas = extract_data_from_markdown_beleza(markdown_content)
            else:
                print(f'URL não reconhecida: {url}')
                return []

            if not lojas:
                print(f'Sem dados ou SKU não encontrado para {url}')
                return []
            return lojas
        except PlaywrightError as e:
            print(f'Erro do Playwright na tentativa {attempt + 1}: {e}')
            if attempt < max_retries - 1:
                print('Tentando novamente...')
                await asyncio.sleep(2)
            else:
                print(f'Erro ao crawlear a URL {url} após {max_retries} tentativas: {e}')
                return []
        except Exception as e:
            print(f'Erro ao crawlear a URL {url} na tentativa {attempt + 1}: {e}')
            return []

async def send_to_api(data):
    """Envia os dados dos vendedores para a API (POST)."""
    api_url = os.environ.get('API_URL', 'https://www.price.kamico.com.br/api/products')
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_url, json=data, headers={'Content-Type': 'application/json'}) as response:
                print(f"Status da resposta (POST): {response.status}")
                return response.status
        except Exception as e:
            print(f"Erro ao enviar dados para a API (POST): {e}")
            return None

async def update_to_api(data):
    """Atualiza os dados dos vendedores na API (PUT)."""
    api_url = 'https://www.price.kamico.com.br/api/products'
    async with aiohttp.ClientSession() as session:
        try:
            async with session.put(
                api_url,
                json=data,
                headers={'Content-Type': 'application/json'},
            ) as response:
                print(f'Status da resposta (PUT): {response.status}')
                return response.status
        except Exception as e:
            print(f'Erro ao enviar dados para a API (PUT): {e}')
            return None

def save_sem_dados_urls(sem_dados):
    """Salva URLs sem dados em um arquivo JSON."""
    try:
        with open('sem_dados_urls.json', 'w', encoding='utf-8') as f:
            json.dump(sem_dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'Erro ao salvar sem_dados_urls.json: {e}')

def carregar_sem_dados_url():
    """Carrega URLs que falharam em execuções anteriores de um arquivo JSON."""
    try:
        if os.path.exists('sem_dados_urls.json'):
            with open('sem_dados_urls.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        print(f'Erro ao carregar sem_dados_urls.json: {e}')
        return []

async def process_urls(urls):
    """Processa URLs de Amazon, Beleza na Web e Mercado Livre e envia os itens para a API."""
    sem_dado = carregar_sem_dados_url()
    combined_urls = list(dict.fromkeys(sem_dado + urls))
    total_urls = len(combined_urls)
    processed_count = 0
    sem_dados = []
    successful_urls = 0

    print(f'Total de URLs a processar: {total_urls} (incluindo {len(sem_dado)} URLs de execuções anteriores)')
    async with AsyncWebCrawler(verbose=True) as crawler:
        for url in combined_urls:
            processed_count += 1
            print(f'Processado {processed_count}/{total_urls} URLs')
            result = await crawl_url(crawler, url)
            print('Dados extraídos:')
            pprint(result, indent=2)  # Use pprint for structured output
            if result:
                post_status = await send_to_api(result)
                if post_status in (200, 201):
                    print(f'Dados salvos com sucesso para {url}, POST concluído.')
                    successful_urls += 1
                elif post_status == 400:
                    put_status = await update_to_api(result)
                    if put_status != 202:
                        print(f'Falha ao atualizar dados de {url} (Status: {put_status})')
                        sem_dados.append(url)
                    else:
                        print(f'Dados atualizados com sucesso para {url}, PUT concluído.')
                        successful_urls += 1
                else:
                    print(f'Falha ao salvar dados de {url} (Status: {post_status})')
                    sem_dados.append(url)
            else:
                print(f'Sem dados para {url}, marcando para lista de URLs sem dados')
                sem_dados.append(url)
            time.sleep(1)

    save_sem_dados_urls(sem_dados)
    print(f'Processamento concluído: {processed_count}/{total_urls} URLs processadas')
    print(f'Resultados: {successful_urls} URLs bem-sucedidas, {len(sem_dados)} URLs falharam, {len(sem_dados)} URLs sem dados')

if __name__ == "__main__":
    urls = [
        "https://www.belezanaweb.com.br/wella-professionals-invigo-color-brilliance-condicionador-1-litro/ofertas-marketplace",
        "https://www.epocacosmeticos.com.br/pesquisa?q=8005610672427",
        # Adicione outras URLs para Amazon, Beleza na Web, Mercado Livre, etc.
    ]
    asyncio.run(process_urls(urls))
