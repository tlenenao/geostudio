# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class AttachmentPresignRequest(BaseModel):
    fieldKey: str
    filename: str
    contentType: str


class AttachmentPresignResponse(BaseModel):
    uploadUrl: str
    key: str


class AttachmentConfirmRequest(BaseModel):
    key: str
    fieldKey: str
    filename: str
    contentType: str


class AttachmentRead(BaseModel):
    id: str
    fieldKey: str
    filename: str
    contentType: str
    byteSize: int
    createdAt: str


class AttachmentList(BaseModel):
    attachments: list[AttachmentRead]
