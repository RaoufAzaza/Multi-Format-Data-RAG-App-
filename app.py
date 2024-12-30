import os
import gc
import json
import tempfile
import uuid
import pandas as pd
import together
from typing import Optional, Dict, Union

from llama_index.core import Settings, Document, VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.node_parser import MarkdownNodeParser

import streamlit as st

LLAMA_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
MAX_TOKENS = 500
TEMPERATURE = 0.7
EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"

class MultiFormatChatbot:
    def __init__(self):
  
        self.setup_session_state()
        self.embed_model = self.load_embeddings_model()
        Settings.embed_model = self.embed_model

    def setup_session_state(self):
        if "id" not in st.session_state:
            st.session_state.id = uuid.uuid4()
            st.session_state.file_cache = {}
            st.session_state.messages = []
            st.session_state.current_data = None

    @staticmethod
    @st.cache_resource
    def load_embeddings_model():
        return HuggingFaceEmbedding(model_name=EMBEDDING_MODEL, trust_remote_code=True)

    @staticmethod
    @st.cache_data
    def process_excel(file) -> Optional[pd.DataFrame]:
        try:
            return pd.read_excel(file)
        except Exception as e:
            st.error(f"Error processing Excel file: {e}")
            return None

    @staticmethod
    @st.cache_data
    def process_json(file) -> Optional[Dict]:
        try:
            return json.loads(file.getvalue().decode())
        except Exception as e:
            st.error(f"Error processing JSON file: {e}")
            return None

    def create_index(self, data: Union[pd.DataFrame, Dict], file_key: str):
        try:
            if isinstance(data, pd.DataFrame):
                content = data.to_string()
            else:
                content = json.dumps(data, indent=2)

            doc = Document(text=content)
            node_parser = MarkdownNodeParser()
            index = VectorStoreIndex.from_documents(
                documents=[doc],
                transformations=[node_parser],
                show_progress=True
            )
            st.session_state.file_cache[file_key] = index

            del doc, node_parser
            gc.collect()

            return index
        except Exception as e:
            st.error(f"Error creating index: {e}")
            return None

    def query_llama(self, prompt: str, context: Optional[str] = None) -> str:
        try:
            messages = [{"role": "system", "content": "You are a helpful data analysis assistant."}]

            if context:
                messages.append({"role": "system", "content": f"Context:\n{context}"})

            messages.append({"role": "user", "content": prompt})
            formatted_prompt = ""
            for message in messages:
                formatted_prompt += f"{message['role']}: {message['content']}\n"

            response = together.Complete.create(
                model=LLAMA_MODEL,
                prompt=formatted_prompt, 
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
                stop=["Human:", "Assistant:"]
            )

            if 'output' in response and 'choices' in response['output']:
                return response['output']['choices'][0]['text'].strip()
            elif 'choices' in response:
                return response['choices'][0]['text'].strip()
            else:
                return "Error: Could not find the response text in the API output."

        except Exception as e:
            return f"Error: {str(e)}"

    def display_data_preview(self, data: Union[pd.DataFrame, Dict]):
        # Display data preview
        if isinstance(data, pd.DataFrame):
            rows_per_page = st.number_input('Rows per page', min_value=5, max_value=100, value=10)
            num_pages = (len(data) + rows_per_page - 1) // rows_per_page
            page = st.number_input('Page', min_value=1, max_value=num_pages, value=1)
            start_idx = (page - 1) * rows_per_page
            st.dataframe(data.iloc[start_idx:start_idx + rows_per_page])
        else:
            st.json(data)

    def run(self):
        st.title("Multi-Format Data RAG App 🤖")

        api_key = st.sidebar.text_input("Enter your API Key", type="password")

        if not api_key:
            st.warning("API Key field is empty. Enter your API Key to use the chatbot.")
    


        together.api_key = api_key

        with st.sidebar:
            st.header("Upload Data")
            file_type = st.selectbox("Choose file type:", ["Excel (.xlsx)", "JSON (.json)"])

            if file_type == "Excel (.xlsx)":
                uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx"])
                if uploaded_file:
                    data = self.process_excel(uploaded_file)
            else:
                uploaded_file = st.file_uploader("Upload JSON file", type=["json"])
                if uploaded_file:
                    data = self.process_json(uploaded_file)

            if uploaded_file and data is not None:
                file_key = f"{st.session_state.id}-{uploaded_file.name}"
                st.session_state.current_data = data

                with st.spinner("Processing data..."):
                    if file_key not in st.session_state.file_cache:
                        self.create_index(data, file_key)
                    st.success("Ready to chat!")
                    self.display_data_preview(data)

            if st.button("Clear Chat 🗑️"):
                st.session_state.messages = []

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt := st.chat_input("Ask about your data..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            if st.session_state.current_data is None:
                st.error("Please upload a file first!")
                return

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    context = str(st.session_state.current_data) if st.session_state.current_data is not None else None
                    response = self.query_llama(prompt, context)
                    st.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})

if __name__ == "__main__":
    chatbot = MultiFormatChatbot()
    chatbot.run()
