with open('src/rtc/connection.py', encoding='utf-8') as f:
    lines = f.readlines()

new_func_lines = [
    '                def fetch_baseline_component(baseline_ref):\n',
    '                    if not isinstance(baseline_ref, dict):\n',
    '                        return None\n',
    '                    item_id  = baseline_ref.get("itemId", "")\n',
    '                    state_id = baseline_ref.get("stateId", "")\n',
    '                    if not item_id:\n',
    '                        return None\n',
    '                    inline_comp = (baseline_ref.get("component")\n',
    '                                   or baseline_ref.get("com.ibm.team.scm.Component"))\n',
    '                    if isinstance(inline_comp, dict) and inline_comp.get("itemId"):\n',
    '                        comp_item_id = inline_comp["itemId"]\n',
    '                        comp_name = get_component_name(comp_item_id)\n',
    '                        if comp_name:\n',
    '                            return {"name": comp_name, "uuid": comp_item_id,\n',
    '                                    "baseline_uuid": item_id, "state_id": state_id}\n',
    '                    try:\n',
    '                        baseline_url = f"{server_url}/resource/itemOid/com.ibm.team.scm.Baseline/{item_id}"\n',
    '                        baseline_data = self._get_json(session, baseline_url, timeout=25)\n',
    '                        if not baseline_data:\n',
    '                            return None\n',
    '                        comp_ref = (baseline_data.get("component")\n',
    '                                    or baseline_data.get("com.ibm.team.scm.Component"))\n',
    '                        if not isinstance(comp_ref, dict) or not comp_ref.get("itemId"):\n',
    '                            return None\n',
    '                        comp_item_id = comp_ref["itemId"]\n',
    '                        comp_name = get_component_name(comp_item_id)\n',
    '                        if not comp_name:\n',
    '                            return None\n',
    '                        return {"name": comp_name, "uuid": comp_item_id,\n',
    '                                "baseline_uuid": item_id, "state_id": state_id}\n',
    '                    except Exception as e:\n',
    '                        logger.debug(f"fetch_baseline_component error {item_id[:8]}: {e}")\n',
    '                        return None\n',
]

new_lines = lines[:444] + new_func_lines + lines[499:]
with open('src/rtc/connection.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print(f'Done. Was {len(lines)}, now {len(new_lines)} lines')
