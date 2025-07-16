# test_corrections.py
import asyncio
from workflow.devis_workflow import DevisWorkflow
from services.client_validator import ClientValidator

async def test_corrections():
    """Test rapide des corrections"""
    print("🧪 Test des corrections...")
    
    # Test 1: Workflow
    workflow = DevisWorkflow()
    error_response = workflow._build_error_response("Test", "Message de test")
    assert "success" in error_response
    assert error_response["success"] is False
    print("✅ _build_error_response OK")
    
    # Test 2: Extraction unifiée
    extracted = await workflow._extract_info_unified("Test devis", "standard")
    assert "error" not in extracted or extracted.get("error") is None
    print("✅ Extraction unifiée OK")
    
    # Test 3: Validation formats
    from services.client_validator import FormatValidator
    validation = FormatValidator.validate_format("75001", "postal_code", "FR")
    assert validation["valid"] is True
    print("✅ Validation formats OK")
    
    print("🎉 Tous les tests passés !")

if __name__ == "__main__":
    asyncio.run(test_corrections())
    