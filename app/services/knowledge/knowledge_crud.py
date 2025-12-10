# app/services/knowledge/knowledge_crud.py
import logging
import asyncio
from typing import Sequence, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from fastapi import HTTPException

from app.domain.models import (
    Knowledge, 
    KnowledgeCreate, 
    KnowledgeUpdate, 
    KnowledgeRead,
    Document, 
    Experiment,
    UserKnowledgeLink,
    UserKnowledgeRole,
    User,
    ChatSession  # 🟢 导入 ChatSession
)
from app.domain.schemas.knowledge_member import MemberRead

from app.services.knowledge.document_crud import delete_document_and_vectors
from app.services.retrieval import VectorStoreManager
from app.services.factories import setup_embed_model

logger = logging.getLogger(__name__)

# ==========================================
# 权限检查辅助函数
# ==========================================

async def check_privilege(
    db: AsyncSession, 
    knowledge_id: int, 
    user_id: int, 
    required_roles: list[UserKnowledgeRole]
) -> UserKnowledgeLink:
    """
    检查用户在指定知识库中是否具备所需角色之一。
    如果不具备，抛出 403；如果知识库不存在或无关联，抛出 404。
    返回 Link 对象以便后续使用。
    """
    stmt = select(UserKnowledgeLink).where(
        UserKnowledgeLink.knowledge_id == knowledge_id,
        UserKnowledgeLink.user_id == user_id
    )
    result = await db.exec(stmt)
    link = result.first()
    
    if not link:
        # 为了安全，未关联的用户也报 404，防止探测知识库 ID
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    
    if link.role not in required_roles:
        raise HTTPException(
            status_code=403, 
            detail=f"Permission denied. Required roles: {[r.value for r in required_roles]}"
        )
    
    return link

# ==========================================
# 成员管理逻辑
# ==========================================

async def add_member(
    db: AsyncSession,
    knowledge_id: int,
    operator_id: int,
    target_email: str,
    target_role: UserKnowledgeRole
) -> MemberRead:
    """
    邀请成员 (仅 OWNER 可操作)
    """
    # 1. 鉴权: 操作者必须是 OWNER
    await check_privilege(db, knowledge_id, operator_id, [UserKnowledgeRole.OWNER])
    
    # 2. 查找目标用户
    stmt_user = select(User).where(User.email == target_email)
    user_res = await db.exec(stmt_user)
    target_user = user_res.first()
    
    if not target_user:
        raise HTTPException(status_code=404, detail=f"User {target_email} not found")
        
    # 3. 检查是否已存在
    stmt_link = select(UserKnowledgeLink).where(
        UserKnowledgeLink.knowledge_id == knowledge_id,
        UserKnowledgeLink.user_id == target_user.id
    )
    if (await db.exec(stmt_link)).first():
        raise HTTPException(status_code=409, detail="User is already a member")

    # 4. 插入 Link
    new_link = UserKnowledgeLink(
        user_id=target_user.id,
        knowledge_id=knowledge_id,
        role=target_role
    )
    db.add(new_link)
    await db.commit()
    await db.refresh(new_link)
    
    return MemberRead(
        user_id=target_user.id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=new_link.role
    )

async def remove_member(
    db: AsyncSession,
    knowledge_id: int,
    operator_id: int,
    target_user_id: int
):
    """
    移除成员 (仅 OWNER 可操作)
    """
    # 1. 鉴权
    await check_privilege(db, knowledge_id, operator_id, [UserKnowledgeRole.OWNER])
    
    # 2. 获取目标 Link
    stmt = select(UserKnowledgeLink).where(
        UserKnowledgeLink.knowledge_id == knowledge_id,
        UserKnowledgeLink.user_id == target_user_id
    )
    result = await db.exec(stmt)
    target_link = result.first()
    
    if not target_link:
        raise HTTPException(status_code=404, detail="Member not found")
        
    # 防止移除自己导致知识库无 Owner (或者前端做限制，后端兜底)
    # 简单策略：如果是 OWNER 移除 OWNER，需检查是否还有其他 OWNER
    if target_link.role == UserKnowledgeRole.OWNER:
        # 统计剩余 OWNER 数量
        count_stmt = select(UserKnowledgeLink).where(
            UserKnowledgeLink.knowledge_id == knowledge_id,
            UserKnowledgeLink.role == UserKnowledgeRole.OWNER
        )
        owners = (await db.exec(count_stmt)).all()
        if len(owners) <= 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last OWNER")

    await db.delete(target_link)
    await db.commit()

async def get_members(
    db: AsyncSession,
    knowledge_id: int,
    user_id: int
) -> list[MemberRead]:
    """
    获取成员列表 (任意成员可见)
    """
    # 1. 鉴权: 只要在 Link 表里就行
    await check_privilege(db, knowledge_id, user_id, 
                          [UserKnowledgeRole.OWNER, UserKnowledgeRole.EDITOR, UserKnowledgeRole.VIEWER])
    
    # 2. 联表查询 User + Role
    stmt = (
        select(User, UserKnowledgeLink.role)
        .join(UserKnowledgeLink, User.id == UserKnowledgeLink.user_id)
        .where(UserKnowledgeLink.knowledge_id == knowledge_id)
    )
    results = await db.exec(stmt)
    
    members = []
    for user, role in results:
        members.append(MemberRead(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=role
        ))
    return members

async def create_knowledge(
    db: AsyncSession, 
    knowledge_to_create: KnowledgeCreate, 
    user_id: int
) -> Knowledge:
    """
    创建一个新的知识库并绑定到指定用户 (作为 OWNER)。
    """
    logger.info(f"Creating new knowledge base for User {user_id}: {knowledge_to_create.name}")
    
    # 1. 创建 Knowledge 对象 (不带 user_id)
    knowledge_db = Knowledge.model_validate(knowledge_to_create)
    db.add(knowledge_db)
    # Flush 以便获取生成的 ID，但不提交事务
    await db.flush()
    await db.refresh(knowledge_db)
    
    # 2. 创建关联记录 (Link)
    link = UserKnowledgeLink(
        user_id=user_id,
        knowledge_id=knowledge_db.id,
        role=UserKnowledgeRole.OWNER
    )
    db.add(link)
    
    # 3. 提交事务 (原子性：要么都成功，要么都失败)
    await db.commit()
    await db.refresh(knowledge_db)
    
    return knowledge_db

async def get_knowledge_by_id(
    db: AsyncSession, 
    knowledge_id: int, 
    user_id: int
) -> KnowledgeRead: # 修改返回类型提示为 KnowledgeRead
    """
    获取指定 ID 的知识库，并校验用户是否有权访问。
    """
    # 联表查询: 获取 Knowledge 和 对应的 Role
    statement = (
        select(Knowledge, UserKnowledgeLink.role)
        .join(UserKnowledgeLink, Knowledge.id == UserKnowledgeLink.knowledge_id)
        .where(Knowledge.id == knowledge_id)
        .where(UserKnowledgeLink.user_id == user_id)
    )
    
    result = await db.exec(statement)
    row = result.first()
    
    if not row:
        # 保持安全性，未授权也返回 404，防止枚举 ID
        raise HTTPException(status_code=404, detail="Knowledge not found or permission denied")
    
    knowledge_db, role = row
    
    # 将 ORM 对象转换为 Pydantic 对象，并注入 role
    k_data = knowledge_db.model_dump()
    k_data['role'] = role
    
    return KnowledgeRead(**k_data)

async def get_all_knowledges(
    db: AsyncSession, 
    user_id: int, 
    skip: int = 0, 
    limit: int = 100
) -> Sequence[KnowledgeRead]: # 注意返回值类型提示变更
    """
    获取当前用户有权访问的所有知识库列表 (带 Role)。
    """
    # 联表查询 Knowledge 和 Link
    statement = (
        select(Knowledge, UserKnowledgeLink.role)
        .join(UserKnowledgeLink, Knowledge.id == UserKnowledgeLink.knowledge_id)
        .where(UserKnowledgeLink.user_id == user_id)
        .offset(skip)
        .limit(limit)
    )
    result = await db.exec(statement)
    rows = result.all()
    
    # 手动组装 KnowledgeRead
    knowledge_list = []
    for k, role in rows:
        # 将 Knowledge 的字段 dump 出来，再加上 role
        k_data = k.model_dump()
        k_data['role'] = role
        knowledge_list.append(KnowledgeRead(**k_data))
        
    return knowledge_list

async def update_knowledge(
    db: AsyncSession, 
    knowledge_id: int, 
    user_id: int,
    knowledge_to_update: KnowledgeUpdate
) -> Knowledge:
    """
    更新知识库信息。
    需校验是否有编辑权限 (EDITOR 或 OWNER)。
    """
    # 1. 检查权限 (Join Link 表并检查 Role)
    stmt = (
        select(Knowledge, UserKnowledgeLink.role)
        .join(UserKnowledgeLink, Knowledge.id == UserKnowledgeLink.knowledge_id)
        .where(Knowledge.id == knowledge_id)
        .where(UserKnowledgeLink.user_id == user_id)
    )
    result = await db.exec(stmt)
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Knowledge not found")
    
    knowledge_db, role = row
    
    # 权限检查: 只有 EDITOR 和 OWNER 可以修改元数据
    if role not in [UserKnowledgeRole.EDITOR, UserKnowledgeRole.OWNER]:
         raise HTTPException(status_code=403, detail="Permission denied: Need EDITOR or OWNER role")

    # 2. 执行更新
    update_data = knowledge_to_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(knowledge_db, key, value)
    
    db.add(knowledge_db)
    await db.commit()
    await db.refresh(knowledge_db)
    return knowledge_db

async def delete_knowledge_pipeline(
    db: AsyncSession, 
    knowledge_id: int,
    user_id: int
):
    """
    级联删除知识库。
    只有 OWNER 可以删除知识库。
    """
    logger.info(f"User {user_id} 请求级联删除知识库 {knowledge_id}...")
    
    # 1. 权限校验 (查询 Link 获取 Role)
    stmt = (
        select(Knowledge, UserKnowledgeLink)
        .join(UserKnowledgeLink, Knowledge.id == UserKnowledgeLink.knowledge_id)
        .where(Knowledge.id == knowledge_id)
        .where(UserKnowledgeLink.user_id == user_id)
    )
    result = await db.exec(stmt)
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Knowledge not found")
    
    knowledge, link = row
    
    # [Security] 只有 OWNER 可以执行删除操作
    if link.role != UserKnowledgeRole.OWNER:
        raise HTTPException(status_code=403, detail="Operation forbidden: Only OWNER can delete knowledge base")

    # 2. 获取关联文档
    doc_stmt = select(Document).where(Document.knowledge_base_id == knowledge_id)
    result = await db.exec(doc_stmt)
    documents = result.all()
    
    # 3. 删除所有文档 (包含 MinIO 文件和 ES 中的 Vector Documents)
    for doc in documents:
        try:
            await delete_document_and_vectors(db, doc.id) 
        except Exception as e:
            logger.error(f"删除文档 {doc.id} 失败: {e}")

    # Double check 残留
    result_check = await db.exec(doc_stmt)
    remaining_docs = result_check.all()
    for doc in remaining_docs:
        try:
            await delete_document_and_vectors(db, doc.id)
        except Exception:
            pass

    # 4. 删除关联实验
    try:
        exp_statement = select(Experiment).where(Experiment.knowledge_id == knowledge_id)
        exp_result = await db.exec(exp_statement)
        experiments = exp_result.all()
        for exp in experiments:
            await db.delete(exp)
    except Exception as e:
        logger.error(f"删除关联实验失败: {e}")

    # 5. 删除 ES 索引本身
    try:
        collection_name = f"kb_{knowledge.id}"
        embed_model = setup_embed_model(knowledge.embed_model)
        manager = VectorStoreManager(collection_name, embed_model)
        
        await asyncio.to_thread(manager.delete_index)
        logger.info(f"ES 索引 {collection_name} 清理请求已发送。")
    except Exception as e:
        logger.error(f"删除 ES 索引失败 (Resource Leak Warning): {e}")

    # 6. 删除关联的 ChatSessions (防止 IntegrityError)
    # 由于 ChatSession 的 knowledge_id 是非空的，必须先删除会话
    try:
        session_stmt = select(ChatSession).where(ChatSession.knowledge_id == knowledge_id)
        sessions = (await db.exec(session_stmt)).all()
        for s in sessions:
            await db.delete(s)
        logger.info(f"已级联删除 {len(sessions)} 个关联的对话会话。")
    except Exception as e:
        logger.error(f"删除关联 ChatSession 失败: {e}")
        # 如果删除会话失败，后续删除知识库本体大概率会报错，这里让异常冒泡或者记录
        # 我们选择继续，让下面的 transaction 决定命运

    # 7. 删除关联关系 (Link)
    # 虽然数据库级联可能处理，但显式删除更安全
    try:
        link_stmt = select(UserKnowledgeLink).where(UserKnowledgeLink.knowledge_id == knowledge_id)
        links = (await db.exec(link_stmt)).all()
        for l in links:
            await db.delete(l)
    except Exception as e:
        logger.error(f"删除关联 Link 失败: {e}")

    # 8. 删除知识库本体
    try:
        await db.delete(knowledge)
        await db.commit()
        logger.info(f"知识库 {knowledge.name} 删除完成。")
    except Exception as e:
        logger.error(f"删除知识库记录失败: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"删除知识库失败: {str(e)}")