from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.db.template_models import Template, TemplateVersion


async def _commit_and_refresh(session: AsyncSession, *instances: object) -> None:
    try:
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        raise

    for instance in instances:
        await session.refresh(instance)


async def create_template(
    session: AsyncSession,
    *,
    name: str,
    composition_json: str,
    description: str | None = None,
    variable_schema_json: str | None = None,
) -> tuple[Template, TemplateVersion]:
    """Create a template with its initial version (v1) atomically.

    Returns (template, version_1).
    """
    template = Template(name=name, description=description)

    version = TemplateVersion(
        template_id=template.id,
        version_number=1,
        composition=composition_json,
        variable_schema=variable_schema_json,
    )

    template.active_version_id = version.id
    template.variable_schema = variable_schema_json

    session.add(template)
    session.add(version)
    await _commit_and_refresh(session, template, version)
    return template, version


async def get_template_by_id(
    session: AsyncSession,
    template_id: str,
) -> Template | None:
    """Return a template by ID or None if not found."""
    result = await session.execute(select(Template).where(Template.id == template_id))
    return result.scalar_one_or_none()


async def get_active_version(
    session: AsyncSession,
    template: Template,
) -> TemplateVersion | None:
    """Return the active version for a template."""
    if template.active_version_id is None:
        return None
    result = await session.execute(
        select(TemplateVersion).where(TemplateVersion.id == template.active_version_id)
    )
    return result.scalar_one_or_none()


async def get_version_count(
    session: AsyncSession,
    template_id: str,
) -> int:
    """Return the total number of versions for a template."""
    result = await session.execute(
        select(func.count())
        .select_from(TemplateVersion)
        .where(TemplateVersion.template_id == template_id)
    )
    return result.scalar_one()


async def list_templates(
    session: AsyncSession,
    *,
    offset: int = 0,
    limit: int = 20,
    include_deleted: bool = False,
) -> tuple[list[Template], int]:
    """Return paginated template list ordered by created_at DESC.

    By default excludes soft-deleted templates.
    Returns (items, total_count).
    """
    base = select(Template)
    count_stmt = select(func.count()).select_from(Template)

    if not include_deleted:
        base = base.where(Template.is_deleted == False)  # noqa: E712
        count_stmt = count_stmt.where(Template.is_deleted == False)  # noqa: E712

    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()

    query = base.order_by(col(Template.created_at).desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    items = list(result.scalars().all())

    return items, total


async def update_template(
    session: AsyncSession,
    template_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    composition_json: str | None = None,
    variable_schema_json: str | None = None,
) -> tuple[Template, TemplateVersion | None]:
    """Update a template, creating a new immutable version if composition changes.

    Returns (updated_template, new_version_or_none).
    """
    result = await session.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        msg = f"Template {template_id} not found"
        raise ValueError(msg)

    now = datetime.now(tz=UTC)
    new_version: TemplateVersion | None = None

    if name is not None:
        template.name = name
    if description is not None:
        template.description = description

    if composition_json is not None:
        current_max = await session.execute(
            select(func.max(TemplateVersion.version_number)).where(
                TemplateVersion.template_id == template.id
            )
        )
        max_ver = current_max.scalar_one() or 0

        vs_json = variable_schema_json or template.variable_schema
        new_version = TemplateVersion(
            template_id=template.id,
            version_number=max_ver + 1,
            composition=composition_json,
            variable_schema=vs_json,
        )
        session.add(new_version)
        try:
            await session.flush()
        except SQLAlchemyError:
            await session.rollback()
            raise
        template.active_version_id = new_version.id

    if variable_schema_json is not None and composition_json is None:
        template.variable_schema = variable_schema_json

    if composition_json is not None and variable_schema_json is not None:
        template.variable_schema = variable_schema_json

    template.updated_at = now
    session.add(template)
    await _commit_and_refresh(session, template)
    if new_version is not None:
        await session.refresh(new_version)
    return template, new_version


async def soft_delete_template(
    session: AsyncSession,
    template_id: str,
) -> Template:
    """Soft-delete a template by setting is_deleted=True.

    Raises ValueError if already deleted or not found.
    """
    result = await session.execute(select(Template).where(Template.id == template_id))
    template = result.scalar_one_or_none()
    if template is None:
        msg = f"Template {template_id} not found"
        raise ValueError(msg)

    if template.is_deleted:
        msg = f"Template {template.id} is already deleted"
        raise ValueError(msg)

    template.is_deleted = True
    template.updated_at = datetime.now(tz=UTC)
    session.add(template)
    await _commit_and_refresh(session, template)
    return template
