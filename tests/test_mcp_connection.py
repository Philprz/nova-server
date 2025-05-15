# test_mcp_connection.py
import asyncio
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()

async def test_salesforce_mcp():
    print("=== TEST SALESFORCE MCP ===")
    
    # Créer fichier d'entrée temporaire
    input_data = {
        "action": "salesforce_query",
        "params": {
            "query": "SELECT Id, Name FROM Account LIMIT 5"
        }
    }
    
    with open("test_input.json", "w") as f:
        json.dump(input_data, f)
    
    # Chemin du fichier de sortie
    output_path = "test_output.json"
    
    # Exécuter le script MCP
    cmd = [
        sys.executable,
        "salesforce_mcp.py",
        "--input-file", "test_input.json",
        "--output-file", output_path
    ]
    
    print(f"Exécution de la commande: {' '.join(cmd)}")
    
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    print(f"Code retour: {process.returncode}")
    print(f"Stdout: {stdout.decode() if stdout else ''}")
    print(f"Stderr: {stderr.decode() if stderr else ''}")
    
    # Lire le fichier de sortie s'il existe
    if os.path.exists(output_path):
        with open(output_path, "r") as f:
            try:
                result = json.load(f)
                print(f"Résultat: {json.dumps(result, indent=2)}")
            except json.JSONDecodeError:
                print("Impossible de parser le JSON du fichier de sortie")
                with open(output_path, "r") as raw_f:
                    print(f"Contenu brut: {raw_f.read()}")
    else:
        print(f"Fichier de sortie {output_path} inexistant")

if __name__ == "__main__":
    asyncio.run(test_salesforce_mcp())