"""settings.load on each file given (offline): what the loader derives, or the refusal."""
import hashlib
import json
import pathlib
import sys

from aisef2.app import settings

for arg in sys.argv[1:]:
    p = pathlib.Path(arg)
    try:
        st = settings.read(p)
    except settings.SettingsError as e:
        print(f"{p.name}: REFUSED: {e}")
        continue
    print(f"{p.name}: OK sha256={hashlib.sha256(p.read_bytes()).hexdigest()[:16]} route={st.route} provider={st.provider} "
          f"model={st.model} served_model={st.served_model} listed_owner={st.listed_owner} model_limit={st.model_limit} "
          f"api_key_env={st.api_key_env} client_env={st.client_env} budget={st.budget} turns/session={st.max_turns_per_session} "
          f"chat_probes={st.chat_probes} review={json.dumps(st.review, sort_keys=True)} prices={st.prices} "
          f"confinement={st.confinement} endpoint={st.endpoint}")
