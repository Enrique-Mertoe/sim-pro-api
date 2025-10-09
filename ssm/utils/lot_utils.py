"""
Lot metadata utility functions
"""

def update_lot_assignment_counts(lot_number: str) -> bool:
    """
    Update assigned and unassigned SIM counts for a lot based on actual SimCard data
    
    Args:
        lot_number: The lot number to update counts for
        
    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        from ssm.models import LotMetadata, SimCard
        
        lot_metadata = LotMetadata.objects.get(lot_number=lot_number)
        
        # Count actual SIM cards in this lot
        lot_sim_cards = SimCard.objects.filter(lot=lot_number)
        assigned_count = lot_sim_cards.filter(assigned_to_user__isnull=False).count()
        unassigned_count = lot_sim_cards.filter(assigned_to_user__isnull=True).count()
        
        lot_metadata.assigned_sim_count = assigned_count
        lot_metadata.unassigned_sim_count = unassigned_count
        lot_metadata.save(update_fields=['assigned_sim_count', 'unassigned_sim_count'])
        
        return True
        
    except Exception:
        return False