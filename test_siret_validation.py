
import asyncio
import os
import logging
from dotenv import load_dotenv
import sys # For sys.exit

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, # Changed to DEBUG for more verbosity
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)] # Explicitly direct to stdout
)
logger = logging.getLogger(__name__)
logger.info("--- Logging configured ---")

try:
    logger.debug("Attempting to import ClientValidator...")
    from services.client_validator import ClientValidator
    logger.debug("ClientValidator imported successfully.")
except ImportError as e:
    logger.error(f"Failed to import ClientValidator: {e}", exc_info=True)
    logger.error("Please ensure test_siret_validation.py is in the NOVA-SERVER root directory,")
    logger.error("and the 'services' package is accessible.")
    sys.exit(1) # Use sys.exit

async def main_test_logic():
    logger.info("--- main_test_logic started ---")
    # Load environment variables
    logger.debug("Loading .env file...")
    if not load_dotenv():
        logger.warning("Could not load .env file. Make sure it exists in the root directory.")
    else:
        logger.info(".env file loaded (or did not need loading).")

    logger.info(f"INSEE_CONSUMER_KEY is set: {bool(os.getenv('INSEE_CONSUMER_KEY'))}")
    logger.info(f"INSEE_CONSUMER_SECRET is set: {bool(os.getenv('INSEE_CONSUMER_SECRET'))}")

    validator = None
    try:
        logger.debug("Instantiating ClientValidator...")
        validator = ClientValidator()
        logger.info("ClientValidator instantiated.")
        
        test_siret = "18006003800214" 
        logger.info(f"Attempting to validate SIRET: {test_siret}")
        
        result = await validator._validate_siret_insee(test_siret)
        
        logger.info("\nValidation Result:")
        logger.info("--------------------")
        if result.get("valid"):
            data = result.get("data", {})
            logger.info(f"  SIRET Valid: {result['valid']}")
            logger.info(f"  Company Name: {data.get('company_name')}")
            logger.info(f"  Address: {data.get('address')}")
            logger.info(f"  Status: {data.get('status')}")
            logger.info(f"  Is Siege: {data.get('is_siege')}")
            logger.info(f"  Validation Method: {data.get('validation_method')}")
        else:
            logger.info(f"  SIRET Valid: {result.get('valid', False)}")
            logger.info(f"  Error: {result.get('error')}")
            logger.info(f"  Validation Method: {result.get('validation_method')}")

    except Exception as e:
        logger.error(f"\nAn error occurred during the test logic: {e}", exc_info=True)
    finally:
        logger.debug("Entering finally block of main_test_logic.")
        if validator and hasattr(validator, 'http_client') and validator.http_client:
            logger.info("Closing HTTP client.")
            try:
                await validator.http_client.aclose()
                logger.info("HTTP client closed.")
            except Exception as close_err:
                logger.error(f"Error closing HTTP client: {close_err}", exc_info=True)
        else:
            logger.warning("Validator or http_client not available for closing.")
    logger.info("--- main_test_logic finished ---")


if __name__ == "__main__":
    logger.info("--- Script __main__ starting ---")
    try:
        asyncio.run(main_test_logic())
    except Exception as e:
        # This will catch errors from asyncio.run() itself or unhandled errors in main_test_logic
        logger.critical(f"Critical error in asyncio.run or main_test_logic: {e}", exc_info=True)
        # Also print to stderr directly in case logging is broken
        print(f"CRITICAL ERROR (stderr): {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
    logger.info("--- Script __main__ finished ---")
    print("--- Test script finished ---") # Absolute last line
