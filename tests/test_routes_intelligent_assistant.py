import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from main import app


@pytest.mark.asyncio
async def test_start_quote_workflow_waiting_for_input():
    dummy_result = {
        "success": False,
        "workflow_status": "waiting_for_input",
        "message": "Quelle société souhaitez-vous utiliser ?",
        "quick_actions": [
            {"action": "show_clients_list", "label": "Voir les clients", "type": "info"}
        ],
        "suggestions": ["Edge Communications", "Burlington Textiles"]
    }

    with patch("workflow.devis_workflow.DevisWorkflow") as MockWorkflow:
        instance = MockWorkflow.return_value
        instance.process_prompt = AsyncMock(return_value=dummy_result)

        client = TestClient(app)
        response = client.post(
            "/api/assistant/workflow/create_quote", json={"message": "Créer un nouveau devis"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("workflow_status") == "waiting_for_input"
        assert "Erreur" not in data.get("message", "")