import os
import re
import time
import requests
from flask import Flask, render_template, request, redirect, url_for, session
from flask_mysqldb import MySQL
from PIL import Image
import io
import base64
import logging
import json
from datetime import datetime
from functools import wraps
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'sua_chave_secreta_aqui')

# Configuração do MySQL
app.config['MYSQL_HOST'] = 'viaduct.proxy.rlwy.net'  # Apenas o hostname
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'SOiZeRqyiKiUqqCIcdMrGncUJzzRrIji'
app.config['MYSQL_DB'] = 'railway'
app.config['MYSQL_PORT'] = 24171  # Porta externa

# Adicionar logs para debug
logger.info(f"MySQL Host: {app.config['MYSQL_HOST']}")
logger.info(f"MySQL User: {app.config['MYSQL_USER']}")
logger.info(f"MySQL Database: {app.config['MYSQL_DB']}")
logger.info(f"MySQL Port: {app.config['MYSQL_PORT']}")

mysql = MySQL(app)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Mapeamento de bairros
BAIRROS = {
    1: "Barra da Tijuca",
    2: "Recreio dos Bandeirantes",
    3: "Vargem Grande",
    4: "Vargem Pequena",
    5: "Gardênia Azul",
    6: "Cidade de Deus",
    7: "Curicica",
    8: "Taquara",
    9: "Pechincha",
    10: "Freguesia (Jacarepaguá)",
    11: "Camorim",
    12: "Tanque",
    13: "Praça Seca",
    14: "Madureira",
    16: "Cascadura",
    17: "Campinho",
    18: "Méier",
    19: "Engenho de Dentro",
    20: "Vila Isabel",
    21: "Tijuca",
    22: "Maracanã",
    23: "São Cristóvão",
    24: "Centro",
    25: "Flamengo",
    26: "Botafogo",
    27: "Copacabana",
    28: "Ipanema",
    29: "Leblon",
    30: "Jardim Botânico",
    31: "Laranjeiras",
    32: "Cosme Velho",
    33: "Glória",
    34: "Santa Teresa",
    35: "Lapa",
    36: "Penha",
    37: "Olaria",
    38: "Ramos",
    39: "Bonsucesso",
    40: "Ilha do Governador",
    41: "Pavuna",
    42: "Anchieta",
    43: "Guadalupe",
    44: "Deodoro",
    45: "Realengo",
    46: "Bangu",
    47: "Campo Grande",
    48: "Santa Cruz",
    49: "Sepetiba",
    50: "Guaratiba",
    51: "Pedra de Guaratiba",
    52: "Grajaú",
    53: "Engenho Novo",
    54: "Rocha Miranda",
    55: "Higienópolis"
}


# Classe para buscar produtos por imagem
class ProdutoFinder:
    def __init__(self):
        self.driver = None
        self.max_retries = 3
        self.page_load_timeout = 40

    def _convert_image_to_url(self, image):
        """
        Converte uma imagem para URL usando o serviço imgbb
        """
        try:
            if image.mode != 'RGB':
                image = image.convert('RGB')

            img_buffer = io.BytesIO()
            image.save(img_buffer, format='JPEG', quality=95)
            img_buffer.seek(0)

            retries = 3
            for attempt in range(retries):
                try:
                    files = {'image': ('image.jpg', img_buffer, 'image/jpeg')}
                    response = requests.post(
                        'https://api.imgbb.com/1/upload',
                        params={'key': '8234882d2cc5bc9c7f2f239283951076'},
                        files=files,
                        timeout=30
                    )

                    if response.status_code == 200:
                        url = response.json()['data']['url']
                        logger.info(f"Imagem convertida para URL: {url}")
                        return url
                    else:
                        logger.error(f"Erro no upload da imagem: {response.status_code}")
                        if attempt < retries - 1:
                            time.sleep(2)
                            continue
                except Exception as e:
                    logger.error(f"Tentativa {attempt + 1} falhou: {str(e)}")
                    if attempt < retries - 1:
                        time.sleep(2)
                        continue
            return None

        except Exception as e:
            logger.error(f"Erro ao converter imagem: {str(e)}")
            return None

    def _initialize_driver(self):
        chrome_options = Options()

        # Essential configurations
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')

        # Memory optimization
        chrome_options.add_argument('--memory-pressure-off')
        chrome_options.add_argument('--disk-cache-size=1')
        chrome_options.add_argument('--media-cache-size=1')
        chrome_options.add_argument('--disable-application-cache')
        chrome_options.add_argument('--aggressive-cache-discard')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-logging')

        # Performance settings
        prefs = {
            'profile.managed_default_content_settings.images': 2,
            'profile.default_content_settings.images': 2,
            'disk-cache-size': 1,
            'profile.password_manager_enabled': False,
            'profile.default_content_settings.popups': 2,
            'download.prompt_for_download': False,
            'download.default_directory': '/tmp/downloads'
        }
        chrome_options.add_experimental_option('prefs', prefs)

        try:
            service = Service(
                executable_path='/usr/local/bin/chromedriver',
                log_path='/dev/null'  # Disable logging
            )

            self.driver = webdriver.Chrome(
                service=service,
                options=chrome_options
            )

            self.driver.set_page_load_timeout(self.page_load_timeout)
            self.driver.implicitly_wait(10)

            return True
        except Exception as e:
            logger.error(f"Driver initialization failed: {str(e)}")
            if self.driver:
                self.driver.quit()
            return False

    def __del__(self):
        self.cleanup()

    def cleanup(self):
        """Explicit cleanup method"""
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.delete_all_cookies()
                self.driver.quit()
            except Exception as e:
                logger.error(f"Error in cleanup: {str(e)}")
            finally:
                self.driver = None

    def buscar_produtos(self, imagem):
        try:
            if not self.driver and not self._initialize_driver():
                return []

            img_url = self._convert_image_to_url(imagem)
            if not img_url:
                return []

            search_url = f"https://lens.google.com/uploadbyurl?url={img_url}"
            products = []

            for attempt in range(self.max_retries):
                try:
                    self.driver.delete_all_cookies()
                    self.driver.get(search_url)
                    time.sleep(5)  # Reduced wait time

                    products = self._extract_products_selenium()
                    if products:
                        break

                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Search attempt {attempt + 1} failed: {str(e)}")
                    if attempt < self.max_retries - 1:
                        self._initialize_driver()

            return products[:5]  # Limit results to reduce memory usage

        except Exception as e:
            logger.error(f"Product search failed: {str(e)}")
            return []
        finally:
            self.cleanup()  # Ensure cleanup after each search

    def _extract_products_selenium(self):
        """Extrai produtos usando XPath"""
        products = []
        try:
            xpaths = [
                "//div[contains(@class, 'isv-r')]",
                "//div[@class='g' or contains(@class, 'g-card')]",
                "//div[.//h3 or .//a[@href]]",
                "//div[contains(@style, 'background-image')]",
                "//a[.//img]"
            ]

            result_elements = []
            for xpath in xpaths:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    if elements:
                        result_elements.extend(elements)
                        break
                except Exception as e:
                    continue

            result_elements = list(set(result_elements))

            for element in result_elements[:10]:
                try:
                    title = None
                    for xpath in [".//h3", ".//div[contains(@class, 'title')]", ".//a",
                                  ".//span[string-length(text()) > 10]"]:
                        try:
                            title_element = element.find_element(By.XPATH, xpath)
                            title = title_element.text.strip()
                            if title:
                                break
                        except:
                            continue

                    if not title:
                        continue

                    link = None
                    try:
                        link_element = element.find_element(By.XPATH, ".//a")
                        link = link_element.get_attribute('href')
                    except:
                        try:
                            link = element.get_attribute('href')
                        except:
                            continue

                    price = None
                    try:
                        price_text = element.text
                        price_matches = re.findall(r'R\$\s*[\d.,]+|\d+[\d.,]*\s*reais', price_text)
                        if price_matches:
                            price_str = price_matches[0]
                            price = float(re.sub(r'[^\d,.]', '', price_str).replace(',', '.'))
                    except:
                        pass

                    img = None
                    try:
                        img_element = element.find_element(By.XPATH, ".//img")
                        img = img_element.get_attribute('src')
                    except:
                        try:
                            style = element.get_attribute('style')
                            if style and 'background-image' in style:
                                img = re.findall(r'url\(["\']?(.*?)["\']?\)', style)[0]
                        except:
                            pass

                    if title and link:
                        product = {
                            "nome": title,
                            "preco": price,
                            "link": link,
                            "imagem": img
                        }
                        products.append(product)

                except Exception as e:
                    continue

            return products

        except Exception as e:
            logger.error(f"Erro ao extrair produtos: {str(e)}")
            return []


# Decorator para verificar se o usuário está logado
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Validação simples (substitua por uma lógica de autenticação real)
        if username == 'admin' and password == 'admin123':
            session['logged_in'] = True  # Define a sessão como logada
            return redirect(url_for('lista_cadastros'))
        else:
            return "Usuário ou senha inválidos", 401

    return render_template('login.html')


# Instância do ProdutoFinder
finder = ProdutoFinder()


@app.route('/logout')
def logout():
    session.pop('logged_in', None)  # Remove o status de logado da sessão
    return redirect(url_for('login'))


@app.route('/', methods=['GET', 'POST'])
def upload_produto():
    if request.method == 'POST':
        logger.info("Recebida requisição POST")

        # Coleta dos dados do formulário
        form_data = {
            'nome': request.form['nome'],
            'cpf': request.form['cpf'],
            'telefone': request.form['telefone'],
            'email': request.form['email'],
            'produto': request.form['produto'],
            'marca': request.form['marca'],
            'dtCompra': request.form['data_compra'],
            'valor': float(request.form['valor_unitario']) if request.form['valor_unitario'] else 0.0,
            'marcaUso': request.form['marcas_uso'],
            'descricao': request.form['descricao'],
            'altura': float(request.form['altura']) if request.form['altura'] else 0.0,
            'largura': float(request.form['largura']) if request.form['largura'] else 0.0,
            'profundidade': float(request.form['profundidade']) if request.form['profundidade'] else 0.0,
            'quantidade': float(request.form['quantidade']) if request.form['quantidade'] else 0.0,
            'outroBairro': request.form.get('outro_bairro', ''),
            'voltagem': request.form['voltagem'],
            'tipoEstado': request.form['tipo_reparo'],
            'bairro': request.form['bairro'],
            'novo': 1 if 'novo' in request.form.getlist('estado[]') else 0,
            'usado': 1 if 'usado' in request.form.getlist('estado[]') else 0,
            'troca': request.form['aceita_credito'],
            'nf': request.form['possui_nota_fiscal'],
            'sujo': request.form['precisa_limpeza'],
            'mofo': 1 if 'possui_mofo' in request.form.getlist('estado[]') else 0,
            'cupim': 1 if 'possui_cupim' in request.form.getlist('estado[]') else 0,
            'trincado': 1 if 'esta_trincado' in request.form.getlist('estado[]') else 0,
            'desmontagem': request.form['precisa_desmontagem'],
            'status': 'Análise',  # Status padrão
            'urgente': 'não',
        }

        # Processamento da imagem
        if 'imagem' in request.files:
            imagem = request.files['imagem']
            img = Image.open(imagem)
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='JPEG')
            img_str = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
            form_data['foto1'] = img_str

            # Busca de produtos usando a imagem
            produtos_encontrados = finder.buscar_produtos(img)
            links_produto = json.dumps([{"link": p['link'], "valor": p['preco'], "imagem": p['imagem']} for p in produtos_encontrados])
            fotos_produto = json.dumps([p['imagem'] for p in produtos_encontrados])

            form_data['linksProduto'] = links_produto
            form_data['fotosProduto'] = fotos_produto

        # Inserção no banco de dados
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO fichas (
                nome, cpf, telefone, email, produto, desmontagem, marca, dtCompra, valor, valorEstimado,
                marcaUso, descricao, altura, largura, profundidade, foto1, status, urgente, quantidade,
                outroBairro, voltagem, bairro, tipoEstado, novo, usado, troca, nf, sujo, mofo, cupim,
                trincado, linksProduto, fotosProduto
            ) VALUES (
                %(nome)s, %(cpf)s, %(telefone)s, %(email)s, %(produto)s, %(desmontagem)s, %(marca)s,
                %(dtCompra)s, %(valor)s, %(valor)s, %(marcaUso)s, %(descricao)s, %(altura)s, %(largura)s,
                %(profundidade)s, %(foto1)s, %(status)s, %(urgente)s, %(quantidade)s, %(outroBairro)s,
                %(voltagem)s, %(bairro)s, %(tipoEstado)s, %(novo)s, %(usado)s, %(troca)s, %(nf)s, %(sujo)s,
                %(mofo)s, %(cupim)s, %(trincado)s, %(linksProduto)s, %(fotosProduto)s
            )
        """, form_data)
        mysql.connection.commit()
        cur.close()

        return render_template('upload.html')

    return render_template('upload.html')


@app.route('/lista')
@login_required
def lista_cadastros():
    status_filtro = request.args.get('status')
    cur = mysql.connection.cursor()

    if status_filtro:
        cur.execute("SELECT * FROM fichas WHERE status = %s ORDER BY id DESC", (status_filtro,))
    else:
        cur.execute("SELECT * FROM fichas ORDER BY id DESC")

    # Get column names
    columns = [col[0] for col in cur.description]

    # Convert tuples to dictionaries
    fichas = []
    for row in cur.fetchall():
        ficha = dict(zip(columns, row))

        # Convert decimal values to float for proper template rendering
        if ficha['valor'] is not None:
            ficha['valor'] = float(ficha['valor'])
        else:
            ficha['valor'] = 0.0

        # Handle other decimal fields if needed
        for field in ['altura', 'largura', 'profundidade', 'quantidade']:
            if ficha.get(field) is not None:
                ficha[field] = float(ficha[field])
            else:
                ficha[field] = 0.0

        fichas.append(ficha)

    cur.close()
    return render_template('lista.html', fichas=fichas)

@app.route('/detalhes/<int:id>')
@login_required
def detalhes_ficha(id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM fichas WHERE id = %s", (id,))

    # Get column names
    columns = [col[0] for col in cur.description]

    # Convert tuple to dictionary
    row = cur.fetchone()
    if not row:
        cur.close()
        return "Ficha não encontrada", 404

    ficha = dict(zip(columns, row))
    cur.close()

    # Decodifica os links e fotos dos produtos
    ficha['linksProduto'] = json.loads(ficha['linksProduto']) if ficha['linksProduto'] else []
    ficha['fotosProduto'] = json.loads(ficha['fotosProduto']) if ficha['fotosProduto'] else []

    # Ensure valor is a float
    valor_estimado = float(ficha['valor']) if ficha['valor'] is not None else 0.0

    if ficha['desmontagem'] == 'Sim':
        valor_estimado -= 50.00

    if ficha['sujo'] == 'Sim':
        valor_estimado -= 30.00

    # Cálculo da demanda média e alta
    demanda_media = valor_estimado + (valor_estimado * 0.05)
    demanda_alta = valor_estimado + (valor_estimado * 0.10)

    # Adiciona os valores calculados à ficha
    ficha['valorEstimado'] = valor_estimado
    ficha['demandaMedia'] = demanda_media
    ficha['demandaAlta'] = demanda_alta

    # Converter o número do bairro para o nome do bairro
    ficha['bairro_nome'] = BAIRROS.get(int(ficha['bairro']) if ficha['bairro'] else 0, "Bairro não encontrado")

    # Converter a data para o formato brasileiro (DD/MM/AAAA)
    if ficha['dtCompra']:
        data_compra = datetime.strptime(str(ficha['dtCompra']), '%Y-%m-%d')
        ficha['dtCompra_br'] = data_compra.strftime('%d/%m/%Y')
    else:
        ficha['dtCompra_br'] = "Data não informada"

    return render_template('detalhes.html', ficha=ficha)

@app.route('/atualizar_status/  <int:id>', methods=['POST'])
@login_required
def atualizar_status(id):
    novo_status = request.form['status']
    cur = mysql.connection.cursor()
    cur.execute("UPDATE fichas SET status = %s WHERE id = %s", (novo_status, id))
    mysql.connection.commit()
    cur.close()
    return redirect(url_for('detalhes_ficha', id=id))


def create_tables():
    try:
        cur = mysql.connection.cursor()

        # Criar tabela fichas se não existir
        cur.execute("""
        CREATE TABLE IF NOT EXISTS fichas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nome VARCHAR(255),
            cpf VARCHAR(14),
            telefone VARCHAR(20),
            email VARCHAR(255),
            produto VARCHAR(255),
            desmontagem VARCHAR(3),
            marca VARCHAR(255),
            dtCompra DATE,
            valor DECIMAL(10,2),
            valorEstimado DECIMAL(10,2),
            marcaUso VARCHAR(255),
            descricao TEXT,
            altura DECIMAL(10,2),
            largura DECIMAL(10,2),
            profundidade DECIMAL(10,2),
            foto1 LONGTEXT,
            status VARCHAR(50),
            urgente VARCHAR(3),
            quantidade DECIMAL(10,2),
            outroBairro VARCHAR(255),
            voltagem VARCHAR(50),
            bairro VARCHAR(50),
            tipoEstado VARCHAR(50),
            novo TINYINT(1),
            usado TINYINT(1),
            troca VARCHAR(3),
            nf VARCHAR(3),
            sujo VARCHAR(3),
            mofo TINYINT(1),
            cupim TINYINT(1),
            trincado TINYINT(1),
            linksProduto TEXT,
            fotosProduto TEXT
        )
        """)

        mysql.connection.commit()
        logger.info("Tabelas criadas/verificadas com sucesso")
    except Exception as e:
        logger.error(f"Erro ao criar tabelas: {str(e)}")
    finally:
        if 'cur' in locals():
            cur.close()


def check_chrome_version():
    try:
        chrome_version = os.popen('google-chrome --version').read().strip()
        logger.info(f"Chrome version: {chrome_version}")
        chromedriver_version = os.popen('chromedriver --version').read().strip()
        logger.info(f"ChromeDriver version: {chromedriver_version}")
    except Exception as e:
        logger.error(f"Error checking versions: {str(e)}")


@app.route('/test-db')
def test_db():
    try:
        cur = mysql.connection.cursor()
        cur.execute('SELECT 1')
        result = cur.fetchone()
        cur.close()
        return {
            'status': 'success',
            'message': 'Conexão com banco de dados estabelecida',
            'config': {
                'host': app.config['MYSQL_HOST'],
                'port': app.config['MYSQL_PORT'],
                'database': app.config['MYSQL_DB']
            }
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e),
            'config': {
                'host': app.config['MYSQL_HOST'],
                'port': app.config['MYSQL_PORT'],
                'database': app.config['MYSQL_DB']
            }
        }


if __name__ == '__main__':
    with app.app_context():
        create_tables()
    app.run(debug=True)