import asyncio
from pathlib import Path
import time

from dotenv import load_dotenv
import inngest
import os
import requests
import streamlit as st

load_dotenv()

st.set_page_config(page_title="Disc Medicine Knowledge Agent", page_icon="🩸", layout="wide")

DISC_SOURCE_ID = "disc_medicine_articles"
DISC_QUERY = """SELECT id, title, therapeutic_area, program, indication_name, summary, body, source_url
FROM disc_medicine_articles
ORDER BY id"""

st.markdown(
    """
    <style>
    :root {
        --disc-red: #9f1d35;
        --disc-red-dark: #651426;
        --disc-rose: #f7e8ea;
        --disc-ink: #17212b;
        --disc-blue: #1f5d73;
        --disc-gold: #c9943b;
        --disc-muted: #667085;
        --disc-line: #e6d9da;
    }
    .stApp {
        background:
            radial-gradient(circle at 82% 10%, rgba(159, 29, 53, 0.14), transparent 28%),
            linear-gradient(180deg, #fff8f8 0%, #ffffff 38%, #f6f8fa 100%);
        color: var(--disc-ink);
    }
    .block-container {
        padding-top: 2rem;
        max-width: 1180px;
    }
    h1, h2, h3 {
        color: var(--disc-ink);
        letter-spacing: 0;
    }
    .disc-hero {
        border: 1px solid rgba(159, 29, 53, 0.16);
        border-radius: 8px;
        padding: 28px 32px;
        background:
            linear-gradient(135deg, rgba(255, 255, 255, 0.94), rgba(247, 232, 234, 0.72)),
            radial-gradient(circle at 12% 18%, rgba(159, 29, 53, 0.18), transparent 18%);
        box-shadow: 0 18px 42px rgba(23, 33, 43, 0.08);
        margin-bottom: 24px;
    }
    .disc-kicker {
        color: var(--disc-red);
        font-size: 0.78rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 8px;
    }
    .disc-title {
        font-size: 2.6rem;
        line-height: 1.05;
        font-weight: 800;
        margin: 0 0 12px 0;
    }
    .disc-copy {
        color: #40505c;
        max-width: 760px;
        font-size: 1.02rem;
        line-height: 1.6;
        margin: 0;
    }
    .metric-band {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 12px;
        margin: 20px 0 10px;
    }
    .metric-tile {
        border: 1px solid var(--disc-line);
        border-radius: 8px;
        background: rgba(255,255,255,0.86);
        padding: 16px;
    }
    .metric-label {
        color: var(--disc-muted);
        font-size: 0.78rem;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.05em;
    }
    .metric-value {
        color: var(--disc-red-dark);
        font-size: 1.1rem;
        font-weight: 800;
        margin-top: 4px;
    }
    div[data-testid="stTabs"] button[role="tab"] {
        font-weight: 700;
    }
    .stButton button, .stFormSubmitButton button {
        background: var(--disc-red);
        color: white;
        border: 1px solid var(--disc-red);
        border-radius: 6px;
        font-weight: 750;
    }
    .stButton button:hover, .stFormSubmitButton button:hover {
        background: var(--disc-red-dark);
        color: white;
        border-color: var(--disc-red-dark);
    }
    div[data-testid="stTextInput"] input, textarea, div[data-testid="stNumberInput"] input {
        border-radius: 6px;
    }
    .answer-panel {
        border-left: 4px solid var(--disc-red);
        background: #ffffff;
        border-radius: 8px;
        padding: 18px 20px;
        box-shadow: 0 12px 26px rgba(23, 33, 43, 0.06);
    }
    @media (max-width: 800px) {
        .metric-band { grid-template-columns: 1fr; }
        .disc-title { font-size: 2rem; }
        .disc-hero { padding: 22px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    return inngest.Inngest(app_id="ragproductionapp", is_production=False)


def _inngest_api_base() -> str:
    return os.getenv("INNGEST_API_BASE", "http://127.0.0.1:8288/v1")


def fetch_runs(event_id: str) -> list[dict]:
    url = f"{_inngest_api_base()}/events/{event_id}/runs"
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])


def wait_for_run_output(event_id: str, timeout_s: float = 120.0, poll_interval_s: float = 0.5) -> dict:
    start = time.time()
    last_status = None
    while True:
        runs = fetch_runs(event_id)
        if runs:
            run = runs[0]
            status = run.get("status")
            last_status = status or last_status
            if status in ("Completed", "Succeeded", "Success", "Finished"):
                return run.get("output") or {}
            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Function run {status}")
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Timed out waiting for run output (last status: {last_status})")
        time.sleep(poll_interval_s)


def save_uploaded_pdf(file) -> Path:
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.name
    file_bytes = file.getbuffer()
    file_path.write_bytes(file_bytes)
    return file_path


async def send_event(name: str, data: dict) -> str:
    client = get_inngest_client()
    result = await client.send(inngest.Event(name=name, data=data))
    return result[0]


def csv_to_list(value: str) -> list[str] | None:
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


st.markdown(
    """
    <section class="disc-hero">
      <div class="disc-kicker">Hematology knowledge operations</div>
      <div class="disc-title">Disc Medicine Knowledge Agent</div>
      <p class="disc-copy">
        Search across curated hematology content, sync structured warehouse records, and keep retrieval grounded in source-aware metadata.
      </p>
      <div class="metric-band">
        <div class="metric-tile"><div class="metric-label">Focus</div><div class="metric-value">Blood disorders</div></div>
        <div class="metric-tile"><div class="metric-label">Biology</div><div class="metric-value">Heme + iron</div></div>
        <div class="metric-tile"><div class="metric-label">Source</div><div class="metric-value">Warehouse RAG</div></div>
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)

search_tab, sync_tab, pdf_tab = st.tabs(["Ask", "Warehouse", "PDF"])

with search_tab:
    left, right = st.columns([0.66, 0.34], gap="large")
    with left:
        st.subheader("Ask a hematology question")
        with st.form("rag_query_form"):
            question = st.text_input("Question", placeholder="How does DISC-0974 relate to hepcidin suppression?")
            top_k = st.number_input("Retrieved chunks", min_value=1, max_value=20, value=5, step=1)
            source_filter = st.text_input("Source filter", value=DISC_SOURCE_ID)
            submitted = st.form_submit_button("Ask")

            if submitted and question.strip():
                payload = {
                    "question": question.strip(),
                    "top_k": int(top_k),
                }
                if source_filter.strip():
                    payload["filters"] = {"source": source_filter.strip()}

                with st.spinner("Retrieving source-grounded context..."):
                    event_id = asyncio.run(send_event("rag/query_pdf_ai", payload))
                    output = wait_for_run_output(event_id)
                    answer = output.get("answer", "")
                    sources = output.get("sources", [])

                st.markdown("<div class='answer-panel'>", unsafe_allow_html=True)
                st.subheader("Answer")
                st.write(answer or "(No answer)")
                if sources:
                    st.caption("Sources")
                    for source in sources:
                        st.write(f"- {source}")
                st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.subheader("Suggested prompts")
        st.write("What is the difference between hepcidin suppression and hepcidin induction?")
        st.write("Which Disc Medicine programs are related to EPP or XLP?")
        st.write("What metadata should be preserved for biotech RAG governance?")

with sync_tab:
    st.subheader("Sync Disc Medicine article table")
    with st.form("warehouse_sync_form"):
        source_id = st.text_input("Source ID", value=os.getenv("WAREHOUSE_SOURCE_ID", DISC_SOURCE_ID))
        query = st.text_area("SQL query", value=os.getenv("WAREHOUSE_SYNC_QUERY", DISC_QUERY), height=150)
        primary_key_columns = st.text_input("Primary key columns", value=os.getenv("WAREHOUSE_PRIMARY_KEY_COLUMNS", "id"))
        text_columns = st.text_input("Text columns", value=os.getenv("WAREHOUSE_TEXT_COLUMNS", "title,summary,body"))
        metadata_columns = st.text_input(
            "Metadata columns",
            value=os.getenv("WAREHOUSE_METADATA_COLUMNS", "therapeutic_area,program,indication_name,source_url"),
        )
        sync_submitted = st.form_submit_button("Sync warehouse")

        if sync_submitted:
            payload = {
                "source_id": source_id.strip() or DISC_SOURCE_ID,
                "query": query.strip() or None,
                "primary_key_columns": csv_to_list(primary_key_columns),
                "text_columns": csv_to_list(text_columns),
                "metadata_columns": csv_to_list(metadata_columns),
            }
            payload = {key: value for key, value in payload.items() if value is not None}

            with st.spinner("Embedding warehouse records..."):
                event_id = asyncio.run(send_event("rag/sync-warehouse", payload))
                output = wait_for_run_output(event_id)

            st.success(f"Synced {output.get('ingested', 0)} chunks from {output.get('source_id', source_id)}")

with pdf_tab:
    st.subheader("Upload supplemental PDFs")
    uploaded = st.file_uploader("Choose a PDF", type=["pdf"], accept_multiple_files=False)

    if uploaded is not None:
        with st.spinner("Uploading and triggering ingestion..."):
            path = save_uploaded_pdf(uploaded)
            event_id = asyncio.run(
                send_event(
                    "rag/ingest-pdf",
                    {
                        "pdf_path": str(path.resolve()),
                        "source_id": path.name,
                    },
                )
            )
            time.sleep(0.3)
        st.success(f"Triggered ingestion for: {path.name}")
        st.caption(f"Event ID: {event_id}")
