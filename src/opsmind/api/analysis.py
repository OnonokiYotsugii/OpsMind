from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request

from opsmind.llm.client import OpenAICompatibleClient
from opsmind.llm.types import JSONClient
from opsmind.schemas.analysis import AnalysisErrorResponse, AnalysisRequest, AnalysisResponse
from opsmind.services.analysis import analyze_description

router = APIRouter(prefix="/api/v1", tags=["analysis"])


async def get_llm_client(request: Request) -> AsyncIterator[JSONClient]:
    # Per-request client lifetime; no network calls at app startup.
    async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
        yield OpenAICompatibleClient(request.app.state.settings, http)


@router.post(
    "/analyses",
    response_model=AnalysisResponse,
    summary="初步分析用户提供的故障描述（不查询数据库、不写工单）",
    responses={
        status: {"model": AnalysisErrorResponse, "description": description}
        for status, description in {
            422: "输入校验失败",
            502: "模型响应或输出格式错误",
            503: "模型配置、权限、额度或服务不可用",
            504: "模型调用超时",
        }.items()
    },
)
async def create_analysis(
    data: AnalysisRequest,
    client: Annotated[JSONClient, Depends(get_llm_client)],
) -> AnalysisResponse:
    return await analyze_description(data, client)
