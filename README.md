# Colder

Sistema web para salvar, editar e versionar trechos de código.

## Requisitos

- Python 3.8+

## Config 
O arquivo `config.ini` você pode alterar a porta padrão e login default


## Instalação automática e criação do Service via systemd


```bash
sudo chmod +x script.sh
sudo ./install.sh
```

Abra [http://localhost:5000](http://localhost:5000)

Login default:  
`username: admin`  
`password: admin`

## Instalação padrão (sem Service)

```bash
cd Colder
pip install -r requirements.txt
```

## Execução

```bash
python app.py
```

Abra [http://localhost:5000](http://localhost:5000)


Login default:  
`username: admin`  
`password: admin`

## Funcionalidades

- Criar, renomear e deletar documentos
- Editor com syntax highlighting (CodeMirror)
- Suporte a JavaScript, TypeScript, Python, HTML, CSS, SQL, Bash, JSON, Plaintext
- Versionamento automático (auto-save a cada 2s) e manual
- Histórico de versões com restauração
- Busca em tempo real na sidebar
- Dark / light mode persistido no localStorage