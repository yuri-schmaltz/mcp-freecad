[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/neka-nat-freecad-mcp-badge.png)](https://mseep.ai/app/neka-nat-freecad-mcp)

# FreeCAD MCP

This repository is a FreeCAD MCP that allows you to control FreeCAD from Claude Desktop.

## Demo

### Design a flange

![demo](./assets/freecad_mcp4.gif)

### Design a toy car

![demo](./assets/make_toycar4.gif)

### Design a part from 2D drawing

#### Input 2D drawing

![input](./assets/b9-1.png)

#### Demo

![demo](./assets/from_2ddrawing.gif)

This is the conversation history.
https://claude.ai/share/7b48fd60-68ba-46fb-bb21-2fbb17399b48

## Install addon

FreeCAD Addon directory is:
* Windows: `%APPDATA%\FreeCAD\Mod\`
* Mac: `~/Library/Application\ Support/FreeCAD/Mod/`
* Linux:
  * Ubuntu: `~/.FreeCAD/Mod/` ou `~/snap/freecad/common/Mod/` (se instalar via snap)
  * Debian: `~/.local/share/FreeCAD/Mod`

**Passos para instalação:**
1. Clone o repositório:
   ```bash
   git clone https://github.com/neka-nat/freecad-mcp.git
   cd freecad-mcp
   cp -r addon/FreeCADMCP ~/.FreeCAD/Mod/
   ```
2. Reinicie o FreeCAD.
3. Selecione "MCP Addon" na lista de Workbenches.
4. Inicie o servidor RPC pelo comando "Start RPC Server" na barra de ferramentas "FreeCAD MCP".

## Testes automatizados

Para rodar os testes unitários mínimos:

```bash
pip install pytest
pytest tests/
```

Os testes garantem que o módulo do servidor RPC pode ser importado e que as funções principais existem.

## Troubleshooting e logs

O servidor RPC agora possui logging estruturado (via módulo `logging`).
* Logs de inicialização, parada e erros são emitidos no console.
* Para depuração, verifique a saída do terminal ao iniciar/parar o servidor.

Se encontrar problemas:
* Verifique se as dependências estão instaladas.
* Consulte os logs para mensagens de erro detalhadas.
* Execute os testes para garantir integridade básica.

```bash
git clone https://github.com/neka-nat/freecad-mcp.git
cd freecad-mcp
cp -r addon/FreeCADMCP ~/.FreeCAD/Mod/
```

When you install addon, you need to restart FreeCAD.
You can select "MCP Addon" from Workbench list and use it.

![workbench_list](./assets/workbench_list.png)

And you can start RPC server by "Start RPC Server" command in "FreeCAD MCP" toolbar.

![start_rpc_server](./assets/start_rpc_server.png)

## Setting up Claude Desktop

Pre-installation of the [uvx](https://docs.astral.sh/uv/guides/tools/) is required.

And you need to edit Claude Desktop config file, `claude_desktop_config.json`.

For user.

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": [
        "freecad-mcp"
      ]
    }
  }
}
```

If you want to save token, you can set `only_text_feedback` to `true` and use only text feedback.

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": [
        "freecad-mcp",
        "--only-text-feedback"
      ]
    }
  }
}
```


For developer.
First, you need clone this repository.

```bash
git clone https://github.com/neka-nat/freecad-mcp.git
```

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/freecad-mcp/",
        "run",
        "freecad-mcp"
      ]
    }
  }
}
```

## Tools

* `create_document`: Create a new document in FreeCAD.
* `create_object`: Create a new object in FreeCAD.
* `edit_object`: Edit an object in FreeCAD.
* `delete_object`: Delete an object in FreeCAD.
* `execute_code`: Execute arbitrary Python code in FreeCAD.
* `insert_part_from_library`: Insert a part from the [parts library](https://github.com/FreeCAD/FreeCAD-library).
* `get_view`: Get a screenshot of the active view.
* `get_objects`: Get all objects in a document.
* `get_object`: Get an object in a document.
* `get_parts_list`: Get the list of parts in the [parts library](https://github.com/FreeCAD/FreeCAD-library).

## Contributors

<a href="https://github.com/neka-nat/freecad-mcp/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=neka-nat/freecad-mcp" />
</a>

Made with [contrib.rocks](https://contrib.rocks).
