import logging
import re
from operator import itemgetter

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableParallel, RunnableLambda

from agent.gemini_adapter import CustomGeminiAdapter
from config.settings import get_settings
from database.connection import get_db

# Configure module logger
logger = logging.getLogger(__name__)

settings = get_settings()


class AgentService:
    """
    Servicio de agente conversacional que permite consultas en lenguaje natural
    a la base de datos PostgreSQL usando Google Gemini API.
    """
    
    def __init__(self):
        try:
            logger.info("Initializing AgentService...")
            self.db = get_db()
            logger.info("Database connected successfully.")
            
            target_model = settings.MODEL_NAME
            logger.info(f"Using Google GenAI SDK (Custom Adapter): {target_model}")
            self.llm = CustomGeminiAdapter(
                api_key=settings.GOOGLE_API_KEY,
                model_name=target_model,
                temperature=0
            )
            
            logger.info("LLM initialized.")
            self.sql_chain = self._build_chain()
            logger.info("Chain built successfully.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e

    def _build_chain(self):
        """
        Constructs a multipurpose chain that routes between:
        1. SQL Database Query (for data questions)
        2. General Chat (for greetings/other questions)
        """
        try:
            logger.info("Beginning _build_chain (Multipurpose)...")
            
            # --- ROUTER COMPONENT ---
            router_template = """Given the user question below, classify it into one of two categories:
1. "SQL": If the question requires looking up data in the database tables: {table_names}.
2. "CHAT": If the question is a general greeting, a question about usage, or does not require database access.

Do not generate code. Return ONLY the word "SQL" or "CHAT".

Question: {question}
Classification:"""
            
            def get_table_names(_):
                return ", ".join(self.db.get_usable_table_names())

            router_prompt = PromptTemplate.from_template(router_template)
            
            router_chain = (
                RunnableParallel({
                    "question": itemgetter("question"),
                    "table_names": RunnableLambda(get_table_names)
                })
                | router_prompt
                | self.llm
                | StrOutputParser()
                | RunnableLambda(lambda x: x.strip().upper())
            )

            # --- BRANCH 1: SQL QUERY CHAIN (EXISTING LOGIC) ---
            
            sql_template = """You are a Postgres expert assisting a Chilean Customs Agency (Agencia de Aduanas en Chile).
Given an input question, create a syntactically correct Postgres SQL query to run.
Unless the user specifies in the question a specific number of examples to obtain, query for at most 5 results using the LIMIT clause as per Postgres.
You can order the results to return the most informative data in the database.
Never query for all columns from a table. You must query only the columns that are needed to answer the question.
Wrap each column name in double quotes (") to denote them as delimited identifiers.
Pay attention to use only the column names you can see in the tables below. Be careful to not query for columns that do not exist.
Pay attention to which column is in which table.

IMPORTANT:
- Return ONLY the SQL query.
- Do NOT include any conversational text.
- Just the raw SQL string starting with SELECT.

Only use the following tables:
{table_info}

Question: {question}
SQL Query:"""
            
            sql_prompt = PromptTemplate.from_template(sql_template)
            
            def get_schema(_):
                return self.db.get_table_info()

            generate_sql_chain = (
                RunnableParallel({
                    "question": itemgetter("question"),
                    "table_info": RunnableLambda(get_schema)
                })
                | sql_prompt
                | self.llm
                | StrOutputParser()
            )
            
            def run_query(q):
                logger.debug(f"Executing query: {q}")
                return self.db.run(q)
            
            def execute_sql_step_func(inputs):
                q = inputs["query"]
                logger.debug(f"Raw LLM output: {q}")
                match = re.search(r"```sql\s*(.*?)\s*```", q, re.DOTALL | re.IGNORECASE)
                if match: q = match.group(1).strip()
                else:
                    match = re.search(r"```\s*(.*?)\s*```", q, re.DOTALL)
                    if match: q = match.group(1).strip()
                    else: q = q.replace("```sql", "").replace("```", "").strip()
                
                select_match = re.search(r"(SELECT\s.*)", q, re.DOTALL | re.IGNORECASE)
                if select_match: q = select_match.group(1).strip()
                    
                logger.debug(f"Cleaned SQL query: {q}")
                
                return {
                    "question": inputs["question"],
                    "query": q,
                    "result": run_query(q)
                }
            
            sql_answer_prompt = PromptTemplate.from_template(
                """Given the following user question, corresponding SQL query, and SQL result, answer the user question.
You are an expert assistant for a Customs Agency in Chile.
IMPORTANT: Answer in SPANISH.
Provide a direct and professional answer based ONLY on the result.
Do NOT explain how the SQL query works.
Do NOT mention technical details like 'COUNT', 'SELECT', 'table', or 'row'.

Question: {question}
SQL Query: {query}
SQL Result: {result}
Answer: """
            )

            sql_full_chain = (
                RunnableParallel({"question": itemgetter("question"), "query": generate_sql_chain})
                | RunnableLambda(execute_sql_step_func)
                | sql_answer_prompt
                | self.llm
                | StrOutputParser()
            )

            # --- BRANCH 2: GENERAL CHAT CHAIN ---
            
            chat_template = """You are a helpful AI assistant for a Customs Agency in Chile (Agencia de Aduanas).
Answer the user's question politely and concisely in SPANISH.
If they ask for data you don't have access to, explain that you can only query the 'despachos' and 'documentos' database.

IMPORTANT DOMAIN KNOWLEDGE:
- DUS = Documento Único de Salida (Exportación). NOT "Unidad de Sitio".
- DIN = Declaración de Ingreso.
- MIC/DTA = Manifiesto Internacional de Carga / Declaración de Tránsito Aduanero.
- CRT = Carta de Porte por Carretera.

Question: {question}
Answer:"""
            
            chat_prompt = PromptTemplate.from_template(chat_template)
            
            chat_chain = (
                chat_prompt
                | self.llm
                | StrOutputParser()
            )

            # --- MAIN ROUTING LOGIC ---
            
            def route(info):
                intent = info["intent"]
                if "SQL" in intent:
                    return sql_full_chain
                else:
                    return chat_chain

            full_chain = (
                RunnableParallel({
                    "question": itemgetter("question"),
                    "intent": router_chain
                })
                | RunnableLambda(route)
            )
            
            logger.info("Multipurpose chain built successfully!")
            return full_chain
            
        except Exception as e:
            logger.error(f"Error in _build_chain: {e}", exc_info=True)
            raise e

    async def ask(self, question: str) -> str:
        """
        Process a natural language question and return the answer.
        """
        try:
            # Invoke the chain
            response = await self.sql_chain.ainvoke({"question": question})
            return response
        except Exception as e:
            return f"Lo siento, ocurrió un error al procesar tu consulta: {str(e)}"

# Singleton
_service = None

def get_agent_service() -> AgentService:
    global _service
    if _service is None:
        _service = AgentService()
    return _service
