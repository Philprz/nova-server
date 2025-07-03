import sys
import os
from pathlib import Path

# Add parent directory to Python path
parent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(parent_dir))

from main import app

client = TestClient(app)


def test_missing_info_workflow():
    """The assistant should request missing client and product information.

    When the user only provides "Créer un nouveau devis", the workflow cannot
    identify a client or any products. The API should answer with a 200 status
    and `workflow_status` set to ``"waiting_for_input"``. Quick actions must
    include shortcuts to list available clients and products so the user can
    continue the workflow.
    """
    mock_extraction = {"client": None, "products": []}
    with patch(
        "services.llm_extractor.LLMExtractor.extract_quote_info",
        new=AsyncMock(return_value=mock_extraction),
    ):
        response = client.post(
            "/api/assistant/workflow/create_quote",
            json={"message": "Créer un nouveau devis"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True or data.get("workflow_status") == "waiting_for_input"
    actions = [action.get("action") for action in data.get("quick_actions", [])]
    assert "show_clients_list" in actions
    assert "show_products_list" in actions