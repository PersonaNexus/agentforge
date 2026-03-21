"""Culture API routes — list templates, parse, convert to mixin."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import logging

import yaml
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

router = APIRouter(tags=["culture"])

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "cultures"


@router.get("/culture/list")
async def culture_list() -> list[dict]:
    """List built-in culture templates."""
    templates = []
    if _TEMPLATES_DIR.exists():
        for f in sorted(_TEMPLATES_DIR.glob("*.yaml")):
            data = yaml.safe_load(f.read_text())
            templates.append({
                "name": f.stem,
                "display_name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "value_count": len(data.get("values", [])),
                "yaml": f.read_text(),
            })
    return templates


@router.post("/culture/parse")
async def culture_parse(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form("claude-sonnet-4-20250514"),
) -> dict:
    """Parse a culture file (YAML or markdown) into a CultureProfile."""
    from agentforge.mapping.culture_mapper import CultureParser

    content = await file.read()
    suffix = Path(file.filename or "file.yaml").suffix.lower()

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        if suffix in (".yaml", ".yml"):
            parser = CultureParser()
            profile = parser.parse_yaml(tmp_path)
        else:
            from agentforge.llm.client import LLMClient
            client = LLMClient(model=model)
            parser = CultureParser(llm_client=client)
            profile = parser.parse_file(tmp_path)

        result = json.loads(profile.model_dump_json())

        # Persist culture profile to DB
        sf = getattr(request.app.state, "db_session_factory", None)
        if sf:
            try:
                from agentforge.web.db.repository import CultureRepository

                with sf() as session:
                    repo = CultureRepository(session)
                    repo.save(
                        name=profile.name,
                        description=profile.description,
                        profile_json=result,
                        source_file=file.filename,
                    )
            except Exception:
                logging.getLogger(__name__).exception("Failed to persist culture profile")

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logging.getLogger(__name__).exception("Culture profile parsing failed")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/culture/to-mixin")
async def culture_to_mixin(file: UploadFile = File(...)) -> dict:
    """Convert a CultureProfile YAML into a PersonaNexus mixin."""
    from agentforge.mapping.culture_mapper import CultureMixinConverter, CultureParser

    content = await file.read()
    suffix = Path(file.filename or "file.yaml").suffix.lower()

    if suffix not in (".yaml", ".yml"):
        raise HTTPException(status_code=400, detail="Only YAML files are supported for mixin conversion")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        parser = CultureParser()
        profile = parser.parse_yaml(tmp_path)
        converter = CultureMixinConverter()
        mixin_yaml = converter.convert(profile)
        return {"mixin_yaml": mixin_yaml}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logging.getLogger(__name__).exception("Culture mixin conversion failed")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        tmp_path.unlink(missing_ok=True)
