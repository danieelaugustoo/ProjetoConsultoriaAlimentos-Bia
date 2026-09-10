# Site — Beatriz Vasconcelos, Consultora de Alimentos

Site institucional com uma área de **materiais gratuitos**: o visitante preenche um
formulário (nome, e-mail, empresa, cargo, como conheceu a consultora) e recebe o
material por e-mail, com o PDF anexado e um link de download. A consultora administra
os materiais e vê os leads por um painel próprio em `/admin`.

## Stack

Flask + SQLAlchemy (SQLite) + Jinja. Sem build de front-end. E-mail transacional via
Brevo (API HTTP, com fallback SMTP).

## Estrutura

```
app/                pacote da aplicação (factory, config, models, rotas, e-mail)
  blueprints/       public.py (site) e admin.py (painel)
  emailer/          envio de e-mail, agnóstico de provedor
templates/          páginas Jinja (públicas, admin, e-mail, erros)
static/             css, js, imagens, fontes
instance/           banco, uploads e logs — NÃO versionado, criado em runtime
wsgi.py             ponto de entrada (gunicorn / hospedagem)
```

## Rodando localmente

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt

copy .env.example .env             # e edite os valores
```

No `.env` local, o mínimo para subir:

```
APP_ENV=development
SECRET_KEY=<qualquer coisa>
EMAIL_PROVIDER=console            # não envia e-mail de verdade, só loga
```

```bash
flask --app wsgi create-admin     # cria o login do painel
flask --app wsgi run
```

- Site: http://localhost:5000
- Painel: http://localhost:5000/admin

Gerar uma `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## E-mail (Brevo)

1. Criar conta em https://www.brevo.com (plano gratuito).
2. **Remetente**: o ideal é autenticar o domínio `bvconsultora.com` em
   *Senders, Domains & Dedicated IPs → Domains*. A Brevo mostra alguns registros
   **TXT** (SPF/DKIM) para adicionar no DNS do domínio. Não precisa mexer em MX.
   Depois de autenticado, use `MAIL_FROM=contato@bvconsultora.com`.
   Se não for possível editar o DNS, cadastre o Gmail como *sender* validado e use
   esse endereço no `MAIL_FROM`.
3. Gerar uma **API key** em *SMTP & API → API Keys* e pôr em `BREVO_API_KEY`.
4. `EMAIL_PROVIDER=brevo_api`.

Se a hospedagem bloquear a saída HTTPS para `api.brevo.com`, usar SMTP:

```
EMAIL_PROVIDER=brevo_smtp
BREVO_SMTP_USER=<login SMTP da Brevo>
BREVO_SMTP_PASSWORD=<chave SMTP da Brevo>
```

## Anti-bot (Cloudflare Turnstile) — opcional

Sem isso, o formulário já tem honeypot + limite de 5 envios/hora por IP. Para ativar
o Turnstile: criar um widget grátis em https://dash.cloudflare.com → Turnstile e
preencher no `.env`:

```
TURNSTILE_ENABLED=True
TURNSTILE_SITE_KEY=...
TURNSTILE_SECRET=...
```

## Deploy na hospedagem (bvconsultora.com)

A hospedagem serve a aplicação por WSGI. Passos gerais (cPanel / "Setup Python App"
da Hostinger, ou similar):

1. Enviar o código para a pasta da aplicação (sem `.venv/`, sem `instance/`, sem `.env`).
2. Criar o virtualenv na hospedagem e `pip install -r requirements.txt`.
3. Apontar o **arquivo/entrada WSGI** para `wsgi.py`, objeto `application`.
4. Definir as variáveis de ambiente no painel da hospedagem (não subir `.env`):
   - `APP_ENV=production`
   - `SECRET_KEY=<valor forte e único>`
   - `SESSION_COOKIE_SECURE=True`
   - `SITE_URL=https://bvconsultora.com`
   - `EMAIL_PROVIDER`, `BREVO_API_KEY`, `MAIL_FROM`, `MAIL_FROM_NAME`, `MAIL_REPLY_TO`
   - `TURNSTILE_*` se for usar
5. Garantir que a pasta `instance/` exista e tenha permissão de escrita (o app cria,
   mas o usuário do processo precisa poder escrever). É onde ficam o banco
   (`app.db`), os uploads (`uploads/materiais/`) e os logs.
6. Rodar uma vez, no ambiente da hospedagem:
   ```bash
   flask --app wsgi create-admin
   ```
7. Recarregar a aplicação. Conferir:
   - HTTPS ativo (o site já roda em `bvconsultora.com`).
   - Enviar o formulário de um material com um e-mail real e confirmar o recebimento.

O `.gitignore` já impede subir `.env`, `instance/` e `.venv/`.

## Comandos úteis

```bash
flask --app wsgi create-admin              # cria/atualiza a senha do admin
flask --app wsgi resend-email <lead_id>    # reenvia o material para um lead
flask --app wsgi purge-leads --dias 365    # remove leads antigos (retenção LGPD)
```

## Fluxo de cadastro (double opt-in)

Tanto o formulário de um material quanto o pop-up de entrada criam um lead **não
confirmado** e enviam um e-mail com link de confirmação. Só depois do clique:

- lead de material → recebe o e-mail com o PDF anexado + link de download;
- lead do pop-up → recebe um e-mail de boas-vindas com o link para `/materiais`.

Isso evita cadastro com e-mail falso e uso do envio como disparador de spam.

## Pop-up de entrada

Modal dispensável que aparece uma vez por visitante (controle em `localStorage`).
"Agora não" fecha e o site continua 100% acessível. Ligar/desligar em `POPUP_ENABLED`.

## Segurança (resumo)

- ORM em todas as consultas (sem SQL manual) → sem SQL injection.
- Autoescape do Jinja + sanitização com `bleach` no texto dos materiais → sem XSS
  armazenado. CSP restritiva nos cabeçalhos.
- CSRF em todos os formulários (Flask-WTF).
- Rate limiting: formulário público 5/h por IP; login do admin 5/min por IP;
  confirmação 20/h por IP.
- Anti-bot no formulário: honeypot de campo, honeypot de tempo (envio em menos de 2s
  é recusado), Cloudflare Turnstile (opcional, via `TURNSTILE_*`).
- Bloqueio de e-mail descartável (`app/data/disposable_domains.txt`) e limite de
  3 solicitações por e-mail a cada 24h.
- Double opt-in: nada é enviado antes da confirmação do e-mail.
- Senha do admin com hash scrypt; cookies `HttpOnly`/`Secure`/`SameSite=Lax`.
- Upload valida assinatura do PDF (`%PDF-`) e a imagem via Pillow; arquivos ficam
  fora da raiz web (`instance/uploads/`), servidos só por rota controlada.
- IP dos leads guardado como hash, não em claro. Consentimento LGPD obrigatório e
  registrado; página `/privacidade`.
- Antes de publicar: `pip-audit -r requirements.txt` e `bandit -r app`.

## Mudança de schema durante o desenvolvimento

O projeto não usa Alembic. Se os modelos mudarem, apague `instance/*.db` e rode
`flask --app wsgi create-admin` de novo — o banco é recriado a partir dos modelos.
Em produção o banco já nasce com o schema correto na primeira publicação.
