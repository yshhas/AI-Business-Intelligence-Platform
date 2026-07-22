"""MCP-style read-only tool HTTP adapter (Wave 3 MVP)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_workspace_member
from app.core.db import get_db
from app.models import User, WorkspaceMember
from app.services import mcp_tools
from app.services.mcp_tools import McpError

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/mcp",
    tags=["mcp"],
)


class McpInvokeIn(BaseModel):
    tool: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpInvokeOut(BaseModel):
    tool: str
    result: dict[str, Any]


@router.get("/tools")
def list_mcp_tools(
    workspace_id: UUID,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
) -> dict:
    _user, _member = ctx
    return {"tools": mcp_tools.list_tools()}


@router.post("/invoke", response_model=McpInvokeOut)
def invoke_mcp_tool(
    workspace_id: UUID,
    body: McpInvokeIn,
    ctx: tuple[User, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> McpInvokeOut:
    user, _member = ctx
    try:
        result = mcp_tools.invoke_tool(
            db,
            workspace_id=workspace_id,
            user_id=user.id,
            tool_name=body.tool,
            arguments=body.arguments,
        )
    except McpError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return McpInvokeOut(tool=body.tool, result=result)
