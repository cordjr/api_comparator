# API Comparator - Ferramenta de Comparação e Validação de APIs

API Comparator é uma ferramenta avançada em Python para testar, validar e comparar endpoints de APIs REST. Oferece funcionalidades de validação tradicional e comparação visual entre diferentes endpoints com relatórios HTML detalhados.

## 📋 Índice

- [Instalação e Setup](#instalação-e-setup)
- [Como Usar](#como-usar)
- [Configuração YAML](#configuração-yaml)
- [Funcionalidades](#funcionalidades)
- [Exemplos](#exemplos)

## 🚀 Instalação e Setup

### Pré-requisitos

O projeto requer **Python 3.12+** e o gerenciador de pacotes **uv**. Siga as instruções abaixo para seu sistema operacional:

### Windows

1. **Instalar Python 3.12+**
   ```cmd
   # Baixe e instale o Python do site oficial: https://www.python.org/downloads/
   # Ou use o winget (Windows Package Manager)
   winget install Python.Python.3.12
   ```

2. **Instalar uv**
   ```cmd
   # Via PowerShell
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   
   # Via pip (alternativa)
   pip install uv
   ```

3. **Configurar o projeto**
   ```cmd
   cd caminho\para\projeto
   uv sync
   ```

### macOS

1. **Instalar Python 3.12+**
   ```bash
   # Via Homebrew (recomendado)
   brew install python@3.12
   
   # Via pyenv (alternativa)
   brew install pyenv
   pyenv install 3.12.0
   pyenv global 3.12.0
   ```

2. **Instalar uv**
   ```bash
   # Via curl
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Via Homebrew
   brew install uv
   
   # Via pip (alternativa)
   pip install uv
   ```

3. **Configurar o projeto**
   ```bash
   cd /caminho/para/projeto
   uv sync
   ```

### Linux (Ubuntu/Debian)

1. **Instalar Python 3.12+**
   ```bash
   # Ubuntu 22.04+ / Debian 12+
   sudo apt update
   sudo apt install python3.12 python3.12-venv python3-pip
   
   # Para versões mais antigas, use deadsnakes PPA
   sudo add-apt-repository ppa:deadsnakes/ppa
   sudo apt update
   sudo apt install python3.12 python3.12-venv
   ```

2. **Instalar uv**
   ```bash
   # Via curl
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Via pip
   pip install uv
   ```

3. **Configurar o projeto**
   ```bash
   cd /caminho/para/projeto
   uv sync
   ```

### Linux (CentOS/RHEL/Fedora)

1. **Instalar Python 3.12+**
   ```bash
   # Fedora
   sudo dnf install python3.12 python3-pip
   
   # CentOS/RHEL (com EPEL)
   sudo yum install epel-release
   sudo yum install python3.12 python3-pip
   ```

2. **Instalar uv**
   ```bash
   # Via curl
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Via pip
   pip install uv
   ```

3. **Configurar o projeto**
   ```bash
   cd /caminho/para/projeto
   uv sync
   ```

### Verificação da Instalação

```bash
# Verificar Python
python --version
# Deve mostrar Python 3.12.x ou superior

# Verificar uv
uv --version
# Deve mostrar a versão do uv

# Verificar dependências do projeto
uv run python -c "import requests, yaml, deepdiff; print('✅ Todas as dependências instaladas!')"
```

## 📖 Como Usar

### Execução Básica

```bash
# Usar configuração padrão (api_comparator_config.yaml)
uv run python api_comparator.py

# Usar arquivo de configuração específico
uv run python api_comparator.py -c api_comparator_demo.yaml

# Usar configuração customizada
uv run python api_comparator.py -c minha_configuracao.yaml
```

### Tipos de Validação

O API Comparator suporta dois tipos principais de operação:

1. **Testes Tradicionais**: Validação individual de endpoints
2. **Comparações**: Comparação entre múltiplos endpoints com relatório visual

### Saídas Geradas

- **Console**: Resultados em tempo real com indicadores visuais (✅/❌)
- **JSON**: Relatório detalhado (`api_comparator_results.json`)
- **HTML**: Relatório visual de comparações (`api_comparator_report.html`)

## ⚙️ Configuração YAML

### Estrutura Básica

```yaml
# Configurações globais
config:
  base_url: "https://api.exemplo.com"          # URL base principal
  base_url_comparison: "https://api2.exemplo.com"  # URL base para comparações (opcional)
  timeout: 30                                  # Timeout em segundos
  headers:                                     # Headers globais
    Content-Type: "application/json"
    User-Agent: "API Comparator"
    Authorization: "Bearer {{token}}"          # Suporte a variáveis
  variables:                                   # Variáveis globais
    token: "abc123"
    user_id: "1"

# Testes tradicionais (opcional)
tests:
  - name: "Nome do teste"
    enabled: true                              # true/false para ativar/desativar
    description: "Descrição opcional"
    request:
      method: GET                              # GET, POST, PUT, DELETE, PATCH
      path: "/users/{{user_id}}"              # Suporte a variáveis
      headers:                                 # Headers específicos do teste
        X-Custom-Header: "valor"
      query_params:                            # Query parameters
        filter: "active"
        limit: 10
      body:                                    # Body para POST/PUT/PATCH
        name: "João"
        email: "joao@exemplo.com"
        id: "{{uuid}}"                         # Gera UUID automaticamente
    expected:
      status_code: 200
      headers:                                 # Validação de headers de resposta
        content-type: "application/json"
      body:
        contains: ["name", "email"]            # Strings que devem estar presentes
        exact:                                 # Valores exatos esperados
          status: "success"

# Comparações entre endpoints
comparisons:
  - name: "Comparação entre usuários"
    enabled: true
    endpoints:                                 # Lista de endpoints para comparar
      - name: "Usuário 1"
        request:
          method: GET
          path: "/users/1"
      - name: "Usuário 2"
        request:
          method: GET
          path: "/users/2"
    validation:
      compare_status: true                     # Comparar códigos de status
      compare_body: true                       # Comparar conteúdo do body
      ignore_fields:                           # Campos a ignorar na comparação
        - "root['id']"
        - "root['timestamp']"

  # Sintaxe simplificada para comparar entre hosts diferentes
  - name: "Comparação entre hosts"
    enabled: true
    request:                                   # Um único request testado em ambas as base_urls
      method: GET
      path: "/endpoint"
    validation:
      compare_status: true
      compare_body: false                      # false se esperamos diferenças

# Configurações de relatório
report:
  output_file: "api_comparator_results.json"      # Arquivo JSON de resultados
  comparison_report: "api_comparator_report.html" # Relatório HTML de comparações
  save_results: true                               # Salvar arquivos de saída
  verbose: true                                    # Logs detalhados
  show_response_in_console: true                   # Mostrar responses no console
  format_json_response: true                       # Formatar JSON no console
  max_response_display_length: 2000                # Limite de caracteres (0 = sem limite)
```

### Exemplo Completo Comentado

```yaml
# ===================================================================
# CONFIGURAÇÃO GLOBAL
# ===================================================================
config:
  # URL base principal - usada para testes tradicionais e como primeira URL em comparações
  base_url: "https://jsonplaceholder.typicode.com"
  
  # URL base secundária - usada automaticamente em comparações simplificadas
  base_url_comparison: "https://httpbin.org"
  
  # Timeout para requisições HTTP (segundos)
  timeout: 30
  
  # Headers aplicados a todas as requisições
  headers:
    Content-Type: "application/json"
    User-Agent: "API Comparator v1.0"
    Accept: "*/*"
  
  # Variáveis reutilizáveis em toda a configuração
  variables:
    user_id: "1"
    post_id: "1"
    api_key: "demo123"

# ===================================================================
# TESTES TRADICIONAIS
# ===================================================================
tests:
  # Teste simples de validação
  - name: "Buscar informações do usuário"
    enabled: true
    description: "Valida se a API retorna dados corretos do usuário"
    request:
      method: GET
      path: "/users/{{user_id}}"              # Usa variável definida em config.variables
    expected:
      status_code: 200
      body:
        contains: ["name", "email", "phone"]  # Verifica se estes campos existem
  
  # Teste com POST e validação de resposta
  - name: "Criar novo post"
    enabled: true
    request:
      method: POST
      path: "/posts"
      comparison_path: "/comparison__post" # caso o path para comparação seja diferente do path original
      body:
        title: "Meu post de teste"
        body: "Conteúdo do post"
        userId: "{{user_id}}"
        uuid: "{{uuid}}"                      # Gera UUID único automaticamente
    expected:
      status_code: 201
      body:
        exact:
          userId: 1                           # Valor exato esperado

# ===================================================================
# COMPARAÇÕES ENTRE ENDPOINTS
# ===================================================================
comparisons:
  # Comparação detalhada entre múltiplos endpoints
  - name: "Comparar dados de usuários diferentes"
    enabled: true
    endpoints:
      - name: "Usuário 1"
        request:
          method: GET
          path: "/users/1"
      - name: "Usuário 2"
        request:
          method: GET
          path: "/users/2"
      - name: "Usuário 3"
        request:
          method: GET
          path: "/users/3"
    validation:
      compare_status: true                    # Verificar se status codes são iguais
      compare_body: true                      # Comparar estrutura e conteúdo JSON
      ignore_fields:                          # Campos que devem ser ignorados na comparação
        - "root['id']"                        # ID será diferente
        - "root['name']"                      # Nome será diferente
        - "root['username']"                  # Username será diferente
        - "root['email']"                     # Email será diferente

  # Comparação estrutural (apenas estrutura, não valores)
  - name: "Validar estrutura idêntica entre posts"
    enabled: true
    endpoints:
      - name: "Post 1"
        request:
          method: GET
          path: "/posts/1"
      - name: "Post 2"
        request:
          method: GET
          path: "/posts/2"
    validation:
      compare_status: true
      compare_body: true
      ignore_fields:                          # Ignora todos os valores, compara só estrutura
        - "root['id']"
        - "root['title']"
        - "root['body']"
        - "root['userId']"

  # Comparação que deve falhar (para demonstrar diferenças)
  - name: "Comparação entre tipos diferentes (deve falhar)"
    enabled: true
    endpoints:
      - name: "Post"
        request:
          method: GET
          path: "/posts/1"
      - name: "Usuário"
        request:
          method: GET
          path: "/users/1"
    validation:
      compare_status: true
      compare_body: true                      # Esta comparação falhará propositalmente

  # Sintaxe simplificada: compara o mesmo endpoint em duas URLs base diferentes
  - name: "Comparar resposta entre ambientes"
    enabled: true
    request:                                  # Um único request testado em base_url e base_url_comparison
      method: GET
      path: "/get"                            # Este endpoint existe no httpbin.org mas não no jsonplaceholder
    validation:
      compare_status: false                   # Esperamos status diferentes (404 vs 200)
      compare_body: false                     # Esperamos bodies diferentes

# ===================================================================
# CONFIGURAÇÕES DE RELATÓRIO
# ===================================================================
report:
  # Arquivo JSON com resultados detalhados de todos os testes e comparações
  output_file: "resultados_completos.json"
  
  # Arquivo HTML com visualização das comparações (diff visual)
  comparison_report: "relatorio_comparacoes.html"
  
  # Controles de saída
  save_results: true                          # Salvar arquivos de resultado
  verbose: true                               # Logs detalhados no console
  show_response_in_console: true              # Mostrar responses HTTP no console
  format_json_response: true                  # Formatar JSON para melhor legibilidade
  max_response_display_length: 1500           # Limitar tamanho da resposta exibida (0 = sem limite)
```

## 🌟 Funcionalidades

### Testes Tradicionais
- ✅ Suporte para todos os métodos HTTP (GET, POST, PUT, DELETE, PATCH)
- ✅ Validação de status codes, headers e body
- ✅ Variáveis e placeholders (`{{variavel}}`, `{{uuid}}`)
- ✅ Headers customizados globais e por teste
- ✅ Query parameters e path parameters
- ✅ Relatório JSON detalhado

### Comparações Avançadas
- ✅ Comparação visual entre múltiplos endpoints
- ✅ Relatórios HTML com diff line-by-line e character-level
- ✅ Suporte para ignorar campos específicos na comparação
- ✅ Comparação entre diferentes hosts/ambientes
- ✅ Banners de sucesso/falha para cada comparação
- ✅ Detalhes completos de request para cada endpoint comparado

### Recursos Adicionais
- ✅ Configuração flexível via YAML
- ✅ Sistema de variáveis global
- ✅ Geração automática de UUIDs
- ✅ Timeout configurável
- ✅ Logs detalhados e verbosos
- ✅ Indicadores visuais no console (✅/❌)
- ✅ Formatação automática de JSON

## 📊 Exemplos de Uso

### Teste Simples
```bash
uv run python api_comparator.py -c config_simples.yaml
```

### Comparação entre Ambientes
```bash
# Compara produção vs staging
uv run python api_comparator.py -c comparacao_ambientes.yaml
```

### Validação de APIs Diferentes
```bash
# Compara estruturas de diferentes fornecedores
uv run python api_comparator.py -c comparacao_fornecedores.yaml
```

## 🔧 Solução de Problemas

### Erro: "Arquivo não encontrado"
- Verifique se o arquivo YAML existe no diretório atual
- Use caminho absoluto se necessário

### Erro: "Python 3.12+ required"
- Atualize o Python seguindo as instruções de instalação acima
- Verifique a versão: `python --version`

### Erro: "uv not found"
- Reinstale o uv seguindo as instruções do seu sistema operacional
- Reinicie o terminal após a instalação

### Timeouts de Rede
- Aumente o valor de `timeout` na configuração
- Verifique conectividade com a API

---

Para mais informações e exemplos, consulte os arquivos de configuração de exemplo incluídos no projeto.