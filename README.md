## Como rodar o backend localmente

### Pré-requisitos

- Python 3.10 ou superior
- Git

### 1. Clonar o repositório

```bash
git clone https://github.com/Encosta-AI/Backend.git
cd Backend
```

### 2. Criar o ambiente virtual

**Linux / macOS**
```bash
python3 -m venv .venv
```
> Se der erro, instale o módulo com `sudo apt install python3-venv` e repita.

**Windows**
```powershell
python -m venv .venv
```

### 3. Ativar o ambiente virtual

**Linux / macOS**
```bash
source .venv/bin/activate
```

**Windows (PowerShell)**
```powershell
.venv\Scripts\Activate.ps1
```
> Se aparecer erro de permissão, rode antes:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**Windows (CMD)**
```cmd
.venv\Scripts\activate.bat
```

Quando der certo, o terminal mostra `(.venv)` no início da linha.

### 4. Instalar as dependências

```bash
pip install -r requirements.txt
```

### 5. Iniciar o servidor

Na raiz do projeto (mesma pasta do `requirements.txt`):

```bash
uvicorn backend.main:app --reload
```

O servidor sobe em `http://127.0.0.1:8000`.
A documentação interativa fica em `http://127.0.0.1:8000/docs`.

### 6. Parar o servidor e sair do ambiente

Pressione `Ctrl + C` para parar o servidor e use `deactivate` para sair da venv.

### Observações

- **Não copie nem mova a pasta `.venv`** para outro lugar. Ela guarda caminhos absolutos e para de funcionar. Se mudar o projeto de pasta, apague a `.venv` e repita os passos 2 a 4.
- Para popular o banco com dados iniciais: `python backend/seed.py`
- Para regenerar o modelo de ML: `python ml/gerar_modelo.py`
- Dependências extras: `requirements-lona.txt` (lona) e `requirements-teste.txt` (testes).
