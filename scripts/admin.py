#!/usr/bin/env python3
"""
Admin script for managing clients.
Usage:
    python scripts/admin.py add <client_name>
    python scripts/admin.py list
    python scripts/admin.py remove <client_name>
"""
import sys
import os
from pathlib import Path
import yaml

CLIENTS_DIR = Path(os.getenv("CLIENTS_DIR", "/data/clients"))


def add_client(name: str):
    client_dir = CLIENTS_DIR / name
    client_dir.mkdir(parents=True, exist_ok=True)
    (client_dir / "credentials").mkdir(exist_ok=True)
    
    config = {
        "name": name,
        "hermes_profile": f"{name.lower()}-atendente",
        "timezone": "America/Sao_Paulo",
        "business_hours": {
            "start": "09:00",
            "end": "18:00",
            "days": ["mon", "tue", "wed", "thu", "fri"]
        },
        "meeting_duration": 30,
        "welcome_message": f"Olá! Bem-vindo à {name}."
    }
    
    with open(client_dir / "config.yaml", "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    
    print(f"✅ Cliente '{name}' criado em {client_dir}")
    print(f"   Próximos passos:")
    print(f"   1. Crie profile Hermes: hermes profile create {name.lower()}-atendente")
    print(f"   2. Configure SOUL.md do profile com o prompt")
    print(f"   3. Crie instância Evolution API para {name}")
    print(f"   4. Adicione credenciais Google em {client_dir}/credentials/")


def list_clients():
    if not CLIENTS_DIR.exists():
        print("Nenhum cliente configurado")
        return
    
    clients = [d.name for d in CLIENTS_DIR.iterdir() if d.is_dir() and (d / "config.yaml").exists()]
    print(f"Clientes configurados ({len(clients)}):")
    for c in sorted(clients):
        print(f"  - {c}")


def remove_client(name: str):
    client_dir = CLIENTS_DIR / name
    if not client_dir.exists():
        print(f"❌ Cliente '{name}' não encontrado")
        return
    
    confirm = input(f"Tem certeza que deseja remover '{name}'? (sim/não): ")
    if confirm.lower() == "sim":
        import shutil
        shutil.rmtree(client_dir)
        print(f"✅ Cliente '{name}' removido")
    else:
        print("Cancelado")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    if cmd == "add" and len(sys.argv) >= 3:
        add_client(sys.argv[2])
    elif cmd == "list":
        list_clients()
    elif cmd == "remove" and len(sys.argv) >= 3:
        remove_client(sys.argv[2])
    else:
        print(__doc__)
