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
    source_id: Optional[str] = Query(None, description="Filter by WhatsApp source"),
    source_type: Optional[str] = Query(None, description="Filter by source type (manual, whatsapp, import)"),
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
        if source_id:
            filters["source_id"] = source_id
        if source_type:
            filters["source_type"] = source_type
        if lifecycle_stage:
            filters["lifecycle_stage"] = lifecycle_stage
        filters = await apply_org_filter(user, filters, request)
            
        result = await select(
            table="contacts",
            filters=filters if filters else None,
            limit=limit,
            offset=offset,
        )
        
        contacts_list = result or []
        if not contacts_list:
            return {"status": "success", "data": [], "count": 0}

        source_ids = {c.get("source_id") for c in contacts_list if c.get("source_id")}
        source_map = {}
        if source_ids:
            sources = await select(table="whatsapp_numbers", filters={"id": {"in": list(source_ids)}})
            source_map = {s["id"]: s.get("phone_number", "") for s in (sources or [])}

        contact_ids = [c["id"] for c in contacts_list if c.get("id")]
        all_deals = []
        if contact_ids:
            deals = await select(table="deals", filters={"contact_id": {"in": contact_ids}})
            all_deals = deals or []

        deals_by_contact = {}
        for d in all_deals:
            cid = d.get("contact_id")
            if cid:
                deals_by_contact.setdefault(cid, []).append(d)

        pipeline_ids = {d.get("pipeline_id") for d in all_deals if d.get("pipeline_id")}
        pipeline_map = {}
        if pipeline_ids:
            pipelines = await select(table="pipelines", filters={"id": {"in": list(pipeline_ids)}})
            pipeline_map = {p["id"]: p.get("name", "") for p in (pipelines or [])}

        enriched = []
        for contact in contacts_list:
            source_id = contact.get("source_id")
            if source_id and source_id in source_map:
                contact["source_name"] = source_map[source_id]
            elif source_id:
                contact["source_name"] = "Desconhecido"
            else:
                contact["source_name"] = "Manual"

            contact_deals = deals_by_contact.get(contact.get("id"), [])
            contact["deals_count"] = len(contact_deals)
            contact["deals_value"] = sum(float(d.get("value") or 0) for d in contact_deals)

            pipeline_names = {
                pipeline_map.get(d.get("pipeline_id"), "")
                for d in contact_deals
                if d.get("pipeline_id")
            }
            pipeline_names.discard("")
            contact["pipeline_names"] = list(pipeline_names)

            enriched.append(contact)
        
        return {
            "status": "success",
            "data": enriched,
            "count": len(enriched)
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

        if not is_unrestricted(user):
            contact_org = result[0].get("organization_id")
            if contact_org:
                org_ids = await get_user_org_ids(user["id"])
                if contact_org not in org_ids:
                    raise HTTPException(status_code=403, detail="Sem acesso a esta organização")
            
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
        
        # Get organization_id from request or user's orgs
        if not data.get("organization_id"):
            if is_unrestricted(user):
                # Master/admin_geral - try to get from user's orgs
                org_ids = await get_user_org_ids(user["id"])
                if org_ids:
                    data["organization_id"] = list(org_ids)[0]
            else:
                # Regular user - get from their orgs
                org_ids = await get_user_org_ids(user["id"])
                if org_ids:
                    data["organization_id"] = list(org_ids)[0]
        
        # Add timestamps
        data["created_at"] = datetime.utcnow().isoformat()
        data["updated_at"] = datetime.utcnow().isoformat()
        
        # Remove fields that might cause issues
        data.pop("id", None)
        
        result = await insert(
            table="contacts",
            data=data,
        )
        
        # Handle different result formats
        if isinstance(result, list) and result:
            created = result[0]
        elif isinstance(result, dict):
            created = result
        else:
            created = data
        
        return {
            "status": "success",
            "data": created,
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

        if not is_unrestricted(user):
            existing = await select(table="contacts", filters={"id": contact_id})
            if existing:
                contact_org = existing[0].get("organization_id")
                if contact_org:
                    org_ids = await get_user_org_ids(user["id"])
                    if contact_org not in org_ids:
                        raise HTTPException(status_code=403, detail="Sem acesso a esta organização")
        
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

        if not is_unrestricted(user):
            existing = await select(table="contacts", filters={"id": contact_id})
            if existing:
                contact_org = existing[0].get("organization_id")
                if contact_org:
                    org_ids = await get_user_org_ids(user["id"])
                    if contact_org not in org_ids:
                        raise HTTPException(status_code=403, detail="Sem acesso a esta organização")
        
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
