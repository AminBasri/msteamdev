# src/msteamdev/tools/otobo_ticket_store.py
"""
Persistent OTOBO Ticket Mapping Storage
Provides fallback when Redis cache expires for long-lived incidents.
"""

import json
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# File path for persistent mapping storage
OTOBO_MAPPING_FILE = "/home/crewai/msteamdev/log/otobo_ticket_mapping.json"


def _ensure_mapping_file_exists():
    """Ensure the mapping file and its directory exist."""
    try:
        os.makedirs(os.path.dirname(OTOBO_MAPPING_FILE), exist_ok=True)
        if not os.path.exists(OTOBO_MAPPING_FILE):
            with open(OTOBO_MAPPING_FILE, 'w') as f:
                json.dump({}, f)
            logger.info(f"Created OTOBO mapping file: {OTOBO_MAPPING_FILE}")
    except Exception as e:
        logger.error(f"Failed to ensure mapping file exists: {e}")


def save_otobo_ticket_mapping(incident_number: str, ticket_id: str, ticket_number: str = None) -> bool:
    """
    Persistently save OTOBO ticket mapping to file.
    This provides a fallback when Redis cache expires.
    
    Args:
        incident_number: PagerDuty incident number
        ticket_id: OTOBO ticket ID
        ticket_number: OTOBO ticket number (optional)
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        _ensure_mapping_file_exists()
        
        # Load existing mappings
        mappings = {}
        if os.path.exists(OTOBO_MAPPING_FILE):
            try:
                with open(OTOBO_MAPPING_FILE, 'r') as f:
                    mappings = json.load(f)
            except json.JSONDecodeError:
                logger.warning("Corrupted OTOBO mapping file, creating new one")
                mappings = {}
        
        # Check if mapping already exists
        existing = mappings.get(str(incident_number))
        if existing:
            # Update existing mapping
            existing["last_updated"] = datetime.now(timezone.utc).isoformat()
            if ticket_number:
                existing["ticket_number"] = ticket_number
            logger.info(f"Updated OTOBO ticket mapping for incident {incident_number}")
        else:
            # Add new mapping
            mappings[str(incident_number)] = {
                "ticket_id": ticket_id,
                "ticket_number": ticket_number,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            logger.info(f"Created new OTOBO ticket mapping: incident {incident_number} -> ticket {ticket_id}")
        
        # Save back to file with backup
        backup_file = f"{OTOBO_MAPPING_FILE}.bak"
        if os.path.exists(OTOBO_MAPPING_FILE):
            import shutil
            shutil.copy2(OTOBO_MAPPING_FILE, backup_file)
        
        with open(OTOBO_MAPPING_FILE, 'w') as f:
            json.dump(mappings, f, indent=2)
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to save OTOBO ticket mapping: {e}")
        return False


def get_otobo_ticket_mapping(incident_number: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve OTOBO ticket mapping from persistent storage.
    
    Args:
        incident_number: PagerDuty incident number
        
    Returns:
        Dict with ticket_id, ticket_number, created_at, last_updated if found, None otherwise
    """
    try:
        if not os.path.exists(OTOBO_MAPPING_FILE):
            logger.debug(f"OTOBO mapping file does not exist: {OTOBO_MAPPING_FILE}")
            return None
        
        with open(OTOBO_MAPPING_FILE, 'r') as f:
            mappings = json.load(f)
        
        mapping = mappings.get(str(incident_number))
        if mapping:
            logger.info(f"Retrieved OTOBO ticket mapping from file: incident {incident_number} -> ticket {mapping['ticket_id']}")
            return mapping
        
        logger.debug(f"No OTOBO ticket mapping found for incident {incident_number}")
        return None
        
    except json.JSONDecodeError as e:
        logger.error(f"Corrupted OTOBO mapping file: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to retrieve OTOBO ticket mapping: {e}")
        return None


def update_otobo_ticket_timestamp(incident_number: str) -> bool:
    """
    Update the last_updated timestamp for a ticket mapping.
    
    Args:
        incident_number: PagerDuty incident number
        
    Returns:
        True if updated successfully, False otherwise
    """
    try:
        if not os.path.exists(OTOBO_MAPPING_FILE):
            logger.warning(f"Cannot update timestamp - mapping file does not exist: {OTOBO_MAPPING_FILE}")
            return False
        
        with open(OTOBO_MAPPING_FILE, 'r') as f:
            mappings = json.load(f)
        
        if str(incident_number) in mappings:
            mappings[str(incident_number)]["last_updated"] = datetime.now(timezone.utc).isoformat()
            
            # Create backup before writing
            backup_file = f"{OTOBO_MAPPING_FILE}.bak"
            import shutil
            shutil.copy2(OTOBO_MAPPING_FILE, backup_file)
            
            with open(OTOBO_MAPPING_FILE, 'w') as f:
                json.dump(mappings, f, indent=2)
            
            logger.info(f"Updated timestamp for OTOBO ticket mapping: incident {incident_number}")
            return True
        
        logger.debug(f"No mapping found to update for incident {incident_number}")
        return False
        
    except Exception as e:
        logger.error(f"Failed to update OTOBO ticket timestamp: {e}")
        return False


def get_all_mappings() -> Dict[str, Dict[str, Any]]:
    """
    Get all OTOBO ticket mappings.
    
    Returns:
        Dictionary of all mappings, empty dict if file doesn't exist or error occurs
    """
    try:
        if not os.path.exists(OTOBO_MAPPING_FILE):
            return {}
        
        with open(OTOBO_MAPPING_FILE, 'r') as f:
            return json.load(f)
            
    except Exception as e:
        logger.error(f"Failed to get all mappings: {e}")
        return {}


def delete_otobo_ticket_mapping(incident_number: str) -> bool:
    """
    Delete a ticket mapping (useful for cleanup/testing).
    
    Args:
        incident_number: PagerDuty incident number
        
    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        if not os.path.exists(OTOBO_MAPPING_FILE):
            return False
        
        with open(OTOBO_MAPPING_FILE, 'r') as f:
            mappings = json.load(f)
        
        if str(incident_number) in mappings:
            del mappings[str(incident_number)]
            
            with open(OTOBO_MAPPING_FILE, 'w') as f:
                json.dump(mappings, f, indent=2)
            
            logger.info(f"Deleted OTOBO ticket mapping for incident {incident_number}")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Failed to delete OTOBO ticket mapping: {e}")
        return False


def cleanup_old_mappings(days_old: int = 90) -> int:
    """
    Clean up mappings older than specified days.
    
    Args:
        days_old: Delete mappings older than this many days
        
    Returns:
        Number of mappings deleted
    """
    try:
        if not os.path.exists(OTOBO_MAPPING_FILE):
            return 0
        
        with open(OTOBO_MAPPING_FILE, 'r') as f:
            mappings = json.load(f)
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
        deleted_count = 0
        
        to_delete = []
        for incident_num, mapping in mappings.items():
            try:
                last_updated = datetime.fromisoformat(mapping["last_updated"])
                if last_updated < cutoff_date:
                    to_delete.append(incident_num)
            except (KeyError, ValueError):
                continue
        
        for incident_num in to_delete:
            del mappings[incident_num]
            deleted_count += 1
        
        if deleted_count > 0:
            with open(OTOBO_MAPPING_FILE, 'w') as f:
                json.dump(mappings, f, indent=2)
            
            logger.info(f"Cleaned up {deleted_count} old OTOBO ticket mappings (older than {days_old} days)")
        
        return deleted_count
        
    except Exception as e:
        logger.error(f"Failed to cleanup old mappings: {e}")
        return 0


if __name__ == "__main__":
    # Test the module
    from datetime import timedelta
    
    print("Testing OTOBO Ticket Store...")
    
    # Test save
    print("\n1. Testing save_otobo_ticket_mapping...")
    success = save_otobo_ticket_mapping("TEST1234", "TICKET4567", "TN20250100012")
    print(f"   Save result: {success}")
    
    # Test retrieve
    print("\n2. Testing get_otobo_ticket_mapping...")
    mapping = get_otobo_ticket_mapping("TEST123")
    print(f"   Retrieved mapping: {mapping}")
    
    # Test update timestamp
    print("\n3. Testing update_otobo_ticket_timestamp...")
    success = update_otobo_ticket_timestamp("TEST123")
    print(f"   Update result: {success}")
    
    # Test get all
    print("\n4. Testing get_all_mappings...")
    all_mappings = get_all_mappings()
    print(f"   Total mappings: {len(all_mappings)}")
    
    # Test delete
    print("\n5. Testing delete_otobo_ticket_mapping...")
    success = delete_otobo_ticket_mapping("TEST123")
    print(f"   Delete result: {success}")
    
    print("\nAll tests completed!")