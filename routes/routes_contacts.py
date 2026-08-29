"""Contacts CRM Routes"""
from fastapi import APIRouter, Query, HTTPException, Request
from typing import Optional
from datetime import datetime
import logging

from services.database import select, insert, update, delete, ensure_supabase
from routes.deps import get_current_user, apply_org_filter, is_unrestricted, get_user_org_ids

router = APIRouter(prefix="/crm")
logger = logging.getLogger(__name__)


# GET /crm/contacts - List contacts with filters
@router.get("/contacts")
async def list_contacts(
    request: Request,
    organization_id: Optional[str] = Query(None, description="Filter by organization ID"),
    lifecycle_stage: Optional[str] = Query(None, description="Filter by lifecycle stage"),
    search: Optional[str] = Query(None, description="Search by name, email, or phone"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """List all contacts with optional filters"""
    user = await get_current_user(request)
    try:
        ensure_supabase()
        
        filters = {}
        if organization_id:
            filters["organization_id"] = organization_id
        if lifecycle_stage:
            filters["lifecycle_stage"] = lifecycle_stage
        filters = await apply_org_filter(user, filters)
            
        result = await select(
            table="contacts",
            filters=filters if filters else None,
            limit=limit,
            offset=offset,
            
        )
        
        return {
            "status": "success",
            "data": result,
            "count": len(result) if result else 0
        }
    except Exception as e:
        logger.error(f"Error listing contacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# GET /crm/contacts/{id} - Get single contact
@router.get("/contacts/{contact_id}")
async def get_contact(request: Request, contact_id: str):
    """Get a contact by ID"""
    user = await get_current_user(request)
    try:
        ensure_supabase()
        
        result = await select(
            table="contacts",
            filters={"id": contact_id},
            
        )
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=404, detail="Contact not found")
            
        return {
            "status": "success",
            "data": result[0]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# POST /crm/contacts - Create contact
@router.post("/contacts")
async def create_contact(request: Request, data: dict):
    """Create a new contact"""
    user = await get_current_user(request)
    try:
        ensure_supabase()
        
        if not is_unrestricted(user):
            org_ids = await get_user_org_ids(user["id"])
            if org_ids:
                data["organization_id"] = data.get("organization_id") or list(org_ids)[0]
        
        # Add timestamps
        data["created_at"] = datetime.utcnow().isoformat()
        data["updated_at"] = datetime.utcnow().isoformat()
        
        result = await insert(
            table="contacts",
            data=data,
            
        )
        
        return {
            "status": "success",
            "data": result,
            "message": "Contact created successfully"
        }
    except Exception as e:
        logger.error(f"Error creating contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# PUT /crm/contacts/{id} - Update contact
@router.put("/contacts/{contact_id}")
async def update_contact(request: Request, contact_id: str, data: dict):
    """Update an existing contact"""
    user = await get_current_user(request)
    try:
        ensure_supabase()
        
        # Add updated timestamp
        data["updated_at"] = datetime.utcnow().isoformat()
        
        # Remove id from data if present
        data.pop("id", None)
        
        result = await update(
            table="contacts",
            filters={"id": contact_id},
            data=data,
            
        )
        
        return {
            "status": "success",
            "data": result,
            "message": "Contact updated successfully"
        }
    except Exception as e:
        logger.error(f"Error updating contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# DELETE /crm/contacts/{id} - Delete contact
@router.delete("/contacts/{contact_id}")
async def delete_contact(request: Request, contact_id: str):
    """Delete a contact"""
    user = await get_current_user(request)
    try:
        ensure_supabase()
        
        result = await delete(
            table="contacts",
            filters={"id": contact_id},
            
        )
        
        return {
            "status": "success",
            "message": "Contact deleted successfully"
        }
    except Exception as e:
        logger.error(f"Error deleting contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))
