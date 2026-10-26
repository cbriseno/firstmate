# shellcheck shell=bash
# Optional flow contract for bearings rows and secondmate summaries.
# phase: active|human|dependency|integration|technical|unknown.
# state: executing|waiting|held|ready|unknown; ready distinguishes a queued
# dispatch from a worker's verified done state through next_action/source.
# Reasons and titles are full captured text. Dependencies are home-local backlog
# identities, with canonical state and provenance; absent records stay unknown.
# A declaration is historical evidence, never a substitute for current_state.
# A human hold supplies next_action as its canonical reason text, never executed.
# This projection classifies structured fields only, never prose or vendor UI.
# shellcheck disable=SC2034,SC2016
FM_FLOW_JQ_DEFS='
  def flow_context($record; $current; $declaration; $owner; $records; $decisions):
    ($record.unresolved_blocker_ids // []) as $waiting
    | [($record.blocked_by_ids // $waiting)[] as $id
       | ([$records[] | select(.id == $id)][0]
          // [($record.dependency_records // [])[] | select(.id == $id)][0] // null) as $dep
       | {id:$id,title:($dep.title // $id),owner:$owner,state:($dep.state // "unknown"),
          unresolved:(($waiting | index($id)) != null),
          source:(if $dep == null then "backlog.record.unavailable" else ($dep.source // "backlog.record") end),
          reconciliation_required:($dep.state == "done" and (($waiting | index($id)) != null))}] as $deps
    | ($current.state // "unknown") as $state
    | (if $state == "working" then "active"
       elif ($waiting | length) > 0 then "dependency"
       elif $record.hold_kind == "captain" or any($decisions[]?; .verb == "needs-decision") then "human"
       elif $state == "done" then "integration"
       elif $state == "paused" or $state == "parked" or $state == "blocked" or $state == "failed" then "technical"
       else "unknown" end) as $phase
    | {phase:$phase,title:($record.title // null),
       state:(if $phase == "active" then "executing"
              elif $record.current_role == "held" then "held"
              elif $phase == "dependency" or $phase == "human" or $phase == "technical" then "waiting"
              elif $phase == "integration" or $record.state == "queued" then "ready"
              else "unknown" end),
       owner:$owner,
       reason:(if $record.hold_reason != null then $record.hold_reason
               elif $record.blocked_reason != null then $record.blocked_reason
               elif $state != "unknown" then ($current.detail // $state)
               else ($declaration.note // $current.detail // "Motivo no registrado") end),
       source:(if $record.hold_reason != null then "backlog.hold_reason"
               elif $record.blocked_reason != null then "backlog.blocked_reason"
               elif $state != "unknown" then ("current_state." + ($current.source // "unknown"))
               elif $declaration.note != null then "status.declaration (historical)"
               else "unknown" end),
       declared_state:($declaration.state // null),
       waiting_for:(if ($waiting | length) > 0 then ($deps | map(select(.unresolved) | .title) | join(", "))
                    elif $phase == "human" then "respuesta humana registrada en la decisión"
                    elif $phase == "integration" then "verificación e integración de Firstmate"
                    elif $phase == "technical" then "revisión de la condición técnica declarada"
                    else null end),
       next_action:(if $phase == "active" then "El worker continúa el encargo."
                    elif $phase == "dependency" then "Firstmate revisa las dependencias antes de continuar esta etapa."
                    elif $phase == "human" then ($record.hold_reason // "Firstmate presenta o reconcilia la decisión pendiente.")
                    elif $phase == "integration" then "Firstmate verifica la entrega y aplica la autoridad de integración configurada."
                    elif $phase == "technical" then "Firstmate comprueba el bloqueo o la pausa; el texto declarado no demuestra que haya desaparecido."
                    elif $record.state == "queued" then "Firstmate puede despachar cuando corresponda."
                    else "Firstmate necesita una observación actual; la última declaración se conserva como contexto." end),
       firstmate_action:(if $phase == "active" then "supervisar"
                         elif $phase == "dependency" then "coordinar dependencias"
                         elif $phase == "human" then "gestionar decisión"
                         elif $phase == "integration" then "verificar entrega"
                         elif $phase == "technical" then "revisar condición técnica"
                         else "reconciliar estado" end),
       dependencies:$deps};
'
