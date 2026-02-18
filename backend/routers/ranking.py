from fastapi import APIRouter, HTTPException
from backend.schemas.base import RankingRequest, GenericResponse
from backend.services.context import context
from backend.services.logger import BackendAppLogger
from backend.services.socket_manager import manager
import json
import re
from datetime import datetime
from backend.engine.gemini import call_gemini_with_rotation

router = APIRouter()

def fetch_plan_safe(client_obj, ticker):
    query = """
        SELECT cc.company_card_json, s.historical_level_notes 
        FROM company_cards cc
        JOIN stocks s ON cc.ticker = s.ticker
        WHERE cc.ticker = ? ORDER BY cc.date DESC LIMIT 1
    """
    try:
        rows = client_obj.execute(query, [ticker]).rows
        if rows and rows[0]:
            json_str, notes = rows[0][0], rows[0][1]
            card_data = json.loads(json_str) if json_str else {}
            return {
                "narrative_note": card_data.get('marketNote', 'N/A'),
                "strategic_bias": card_data.get('basicContext', {}).get('priceTrend', 'N/A'),
                "full_briefing": card_data.get('screener_briefing', 'N/A'),
                "key_levels_note": notes,
                "planned_support": card_data.get('technicalStructure', {}).get('majorSupport', 'N/A'),
                "planned_resistance": card_data.get('technicalStructure', {}).get('majorResistance', 'N/A')
            }
    except Exception: pass
    return "No Plan Found in DB"

@router.post("/rank", response_model=GenericResponse)
async def run_ranking(request: RankingRequest):
    logger = BackendAppLogger(manager, task_id="ranking_synthesis")
    await logger.info("🧠 Starting Head Trader Synthesis...")
    
    turso = context.get_db()
    km = context.get_km()
    
    cutoff_dt_str = datetime.strptime(request.simulation_cutoff, '%Y-%m-%d %H:%M:%S').strftime('%H:%M')
    
    # 1. Gather Context
    strategic_plans = {}
    for tkr in request.selected_tickers:
        strategic_plans[tkr] = fetch_plan_safe(turso, tkr)
        
    macro_summary = {
        "bias": request.macro_context.get('marketBias', 'Neutral'),
        "narrative": request.macro_context.get('marketNarrative', 'N/A'),
        "sector_rotation": request.macro_context.get('sectorRotation', {}),
        "key_action": request.macro_context.get('marketKeyAction', 'N/A')
    }
    
    use_full = request.use_full_context
    context_packet = []
    for t in request.selected_tickers:
        card = request.market_cards.get(t)
        plan = strategic_plans.get(t)
        briefing = plan.get('full_briefing', 'N/A') if isinstance(plan, dict) else str(plan or 'N/A')

        if use_full and card and isinstance(card, dict):
            # Full context: use live card data
            pm_migration = [b for b in card.get('value_migration_log', [])
                            if b.get('time_window', '').split(' - ')[0].strip() < cutoff_dt_str]
            ref = card.get('reference_levels', {})
            context_packet.append({
                "ticker": t,
                "THE_ANCHOR (Strategic Plan)": plan or "No Plan Found",
                "THE_DELTA (Live Tape)": {
                    "current_price": ref.get('current_price', 'N/A'),
                    "session_delta_structure": pm_migration,
                    "new_impact_zones_detected": card.get('key_level_rejections', [])
                }
            })
        else:
            # Lite mode OR no live card: use screener briefing from DB
            context_packet.append({
                "ticker": t,
                "screener_briefing": briefing
            })

    # 2. Prompt Construction
    p1 = f"[ROLE]\nYou are Head Trader.\n[GLOBAL MACRO CONTEXT]\n{json.dumps(macro_summary, indent=2)}"
    chunks = [f"[CANDIDATE ANALYSIS - BATCH {i//3 + 1}]\n{json.dumps(context_packet[i:i+3], indent=2)}" for i in range(0, len(context_packet), 3)]
    p2_full = "\n".join(chunks)
    rr_i = "\n- **OVERRIDE: HIGH R/R**: YES." if request.prioritize_rr else ""
    prox_i = "\n- **OVERRIDE: PROXIMITY**: YES." if request.prioritize_prox else ""
    context_mode = "FULL CONTEXT" if use_full else "SCREENER BRIEFING (Token-Saving)"
    p3 = f"[TASK]\nRank Candidates. Return TOP 5 JSON LIST.\n**PARAMS**: context_mode={context_mode}, confluence={request.confluence_mode}{rr_i}{prox_i}\n[JSON SCHEMA]..."
    
    full_prompt = p1 + "\n" + p2_full + "\n" + p3
    
    # 3. Gemini Call
    resp, err = call_gemini_with_rotation(full_prompt, "You are a Head Trader.", None, request.model_name, km)
    
    if resp:
        try:
            match = re.search(r"(\[[\s\S]*\])", resp)
            recommendations = json.loads(match.group(1)) if match else json.loads(resp)
            await logger.success("Head Trader Synthesis Complete.")
            return GenericResponse(status="success", message="Ranking complete", data=recommendations)
        except Exception as e:
            await logger.error(f"JSON Parse Error: {e}")
            raise HTTPException(status_code=500, detail="Failed to parse AI response.")
    else:
        await logger.error(f"Head Trader Failed: {err}")
        raise HTTPException(status_code=500, detail=err)
