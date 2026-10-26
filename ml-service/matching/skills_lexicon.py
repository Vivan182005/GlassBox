"""
Skill lexicon used for keyword scanning on both sides of the match: the resume
and the job description. Each skill has one canonical name plus the aliases an
ATS keyword search would treat as the same thing (JS / JavaScript, k8s /
Kubernetes, ...). Matching on canonical names is what lets "ReactJS" on a
resume count for "React.js" in a JD, the way recruiter-side boolean searches do.

Ambiguous short names (C, R, Go, ...) use case-sensitive patterns that require
a list-like context so prose such as "we go further" doesn't count as Go.
"""
import re
from functools import lru_cache
from typing import Dict, List, Tuple

# (canonical, category, aliases). An alias starting with "re:" is a raw regex
# matched case-sensitively; everything else is a case-insensitive literal.
_SKILLS: List[Tuple[str, str, List[str]]] = [
    # --- Programming languages ---
    ("Python", "Languages", ["python", "python3"]),
    ("Java", "Languages", ["re:(?<![A-Za-z])Java(?!Script|script|[A-Za-z])", "re:(?<![A-Za-z])JAVA(?![A-Za-z])", "core java", "java 8", "java 11", "java 17"]),
    ("JavaScript", "Languages", ["javascript", "js", "es6", "ecmascript", "vanilla js"]),
    ("TypeScript", "Languages", ["typescript", "ts"]),
    ("C++", "Languages", ["c++", "cpp", "c plus plus"]),
    ("C", "Languages", [r"re:(?:^|[\s,/|(:])C(?=\s*[,/|)]|\s+(?:and|programming|language)\b)", "c programming", "ansi c", "embedded c"]),
    ("C#", "Languages", ["c#", "csharp", "c sharp"]),
    ("Go", "Languages", ["golang", r"re:(?:^|[\s,/|(:])Go(?=\s*[,/|)]|\s+(?:lang|language|programming)\b)"]),
    ("Rust", "Languages", ["re:(?<![A-Za-z])Rust(?![A-Za-z])", "rustlang"]),
    ("Kotlin", "Languages", ["kotlin"]),
    ("Swift", "Languages", ["re:(?<![A-Za-z])Swift(?![A-Za-z])", "swiftui"]),
    ("Objective-C", "Languages", ["objective-c", "objective c", "objc"]),
    ("Scala", "Languages", ["scala"]),
    ("Ruby", "Languages", ["re:(?<![A-Za-z])Ruby(?![A-Za-z])"]),
    ("PHP", "Languages", ["php"]),
    ("R", "Languages", [r"re:(?:^|[\s,/|(:])R(?=\s*[,/|)]|\s+(?:programming|language|studio)\b)", "rstudio", "r programming"]),
    ("MATLAB", "Languages", ["matlab"]),
    ("Dart", "Languages", ["re:(?<![A-Za-z])Dart(?![A-Za-z])"]),
    ("Bash", "Languages", ["bash", "shell scripting", "shell script", "zsh"]),
    ("Perl", "Languages", ["perl"]),
    ("Solidity", "Languages", ["solidity"]),
    ("SQL", "Data", ["sql", "t-sql", "pl/sql", "plsql", "ansi sql"]),
    ("HTML", "Frontend", ["html", "html5"]),
    ("CSS", "Frontend", ["css", "css3"]),
    ("Verilog", "Hardware", ["verilog", "systemverilog", "system verilog"]),
    ("VHDL", "Hardware", ["vhdl"]),

    # --- Frontend / mobile ---
    ("React", "Frontend", ["react", "react.js", "reactjs", "react js"]),
    ("Next.js", "Frontend", ["next.js", "nextjs", "next js"]),
    ("Angular", "Frontend", ["angular", "angularjs", "angular.js"]),
    ("Vue.js", "Frontend", ["vue", "vue.js", "vuejs", "nuxt"]),
    ("Svelte", "Frontend", ["svelte", "sveltekit"]),
    ("Redux", "Frontend", ["redux", "redux toolkit"]),
    ("Tailwind CSS", "Frontend", ["tailwind", "tailwindcss", "tailwind css"]),
    ("SASS", "Frontend", ["sass", "scss"]),
    ("Webpack", "Frontend", ["webpack", "vite", "babel"]),
    ("jQuery", "Frontend", ["jquery"]),
    ("React Native", "Mobile", ["react native", "react-native"]),
    ("Flutter", "Mobile", ["flutter"]),
    ("Android", "Mobile", ["android", "android sdk", "jetpack compose"]),
    ("iOS", "Mobile", ["re:(?<![A-Za-z])iOS(?![A-Za-z])", "xcode", "uikit"]),

    # --- Backend / frameworks ---
    ("Node.js", "Backend", ["node.js", "nodejs", "node js", "re:(?<![A-Za-z])Node(?![A-Za-z.])"]),
    ("Express.js", "Backend", ["express.js", "expressjs"]),
    ("NestJS", "Backend", ["nestjs", "nest.js"]),
    ("Django", "Backend", ["django", "django rest framework", "drf"]),
    ("Flask", "Backend", ["flask"]),
    ("FastAPI", "Backend", ["fastapi", "fast api"]),
    ("Spring Boot", "Backend", ["spring boot", "springboot", "spring framework", "spring mvc"]),
    ("Hibernate", "Backend", ["hibernate", "jpa"]),
    (".NET", "Backend", [".net", "dotnet", "asp.net", ".net core"]),
    ("Ruby on Rails", "Backend", ["ruby on rails", "rails"]),
    ("Laravel", "Backend", ["laravel"]),
    ("REST APIs", "Backend", ["rest api", "rest apis", "restful", "restful api", "rest services", "api design", "re:(?<![A-Za-z])REST(?![A-Za-z])"]),
    ("GraphQL", "Backend", ["graphql"]),
    ("gRPC", "Backend", ["grpc", "protobuf", "protocol buffers"]),
    ("Microservices", "Backend", ["microservices", "microservice", "micro-services", "service oriented architecture", "soa"]),
    ("System Design", "Backend", ["system design", "high level design", "low level design", "hld", "lld", "scalable systems"]),
    ("Distributed Systems", "Backend", ["distributed systems", "distributed computing"]),
    ("Data Structures & Algorithms", "CS Fundamentals", ["data structures", "algorithms", "dsa", "data structures and algorithms", "problem solving", "competitive programming", "leetcode"]),
    ("OOP", "CS Fundamentals", ["oop", "oops", "object oriented", "object-oriented", "object oriented programming"]),
    ("Design Patterns", "CS Fundamentals", ["design patterns", "solid principles"]),
    ("Operating Systems", "CS Fundamentals", ["operating systems", "operating system"]),
    ("Computer Networks", "CS Fundamentals", ["computer networks", "networking", "tcp/ip", "tcp ip"]),
    ("Multithreading", "CS Fundamentals", ["multithreading", "multi-threading", "concurrency", "concurrent programming"]),
    ("Unit Testing", "Quality", ["unit testing", "unit tests", "junit", "pytest", "jest", "mocha", "tdd", "test driven development"]),
    ("Test Automation", "Quality", ["test automation", "automation testing", "selenium", "cypress", "playwright", "appium", "testng"]),
    ("Manual Testing", "Quality", ["manual testing", "functional testing", "regression testing", "test cases"]),
    ("API Testing", "Quality", ["api testing", "postman", "rest assured"]),
    ("Performance Testing", "Quality", ["performance testing", "load testing", "jmeter", "k6", "gatling"]),

    # --- Databases ---
    ("PostgreSQL", "Databases", ["postgresql", "postgres", "psql"]),
    ("MySQL", "Databases", ["mysql", "mariadb"]),
    ("MongoDB", "Databases", ["mongodb", "mongo db", "mongo", "mongoose"]),
    ("Redis", "Databases", ["redis"]),
    ("Elasticsearch", "Databases", ["elasticsearch", "elastic search", "opensearch", "elk stack", "elk"]),
    ("Cassandra", "Databases", ["cassandra"]),
    ("DynamoDB", "Databases", ["dynamodb", "dynamo db"]),
    ("Oracle Database", "Databases", ["oracle db", "oracle database", "oracle sql"]),
    ("SQL Server", "Databases", ["sql server", "mssql", "ms sql"]),
    ("SQLite", "Databases", ["sqlite"]),
    ("Firebase", "Databases", ["firebase", "firestore"]),
    ("Supabase", "Databases", ["supabase"]),
    ("Neo4j", "Databases", ["neo4j", "graph database"]),
    ("Vector Databases", "AI / ML", ["vector database", "vector db", "pinecone", "weaviate", "qdrant", "milvus", "chromadb", "chroma db", "faiss", "pgvector"]),

    # --- Cloud / DevOps ---
    ("AWS", "Cloud", ["aws", "amazon web services", "ec2", "s3", "aws lambda", "lambda functions", "cloudformation", "ecs", "eks", "rds", "sagemaker"]),
    ("Azure", "Cloud", ["azure", "microsoft azure", "azure devops"]),
    ("GCP", "Cloud", ["gcp", "google cloud", "google cloud platform", "bigquery", "cloud run", "gke"]),
    ("Docker", "DevOps", ["docker", "dockerfile", "containerization", "containers"]),
    ("Kubernetes", "DevOps", ["kubernetes", "k8s", "helm", "openshift"]),
    ("Terraform", "DevOps", ["terraform", "infrastructure as code", "iac", "pulumi"]),
    ("Ansible", "DevOps", ["ansible", "chef", "puppet"]),
    ("CI/CD", "DevOps", ["ci/cd", "ci cd", "cicd", "continuous integration", "continuous delivery", "continuous deployment", "jenkins", "github actions", "gitlab ci", "circleci", "argo cd", "argocd"]),
    ("Git", "DevOps", ["git", "github", "gitlab", "bitbucket", "version control"]),
    ("Linux", "DevOps", ["linux", "unix", "ubuntu", "centos", "rhel"]),
    ("Nginx", "DevOps", ["nginx", "apache http", "load balancer", "load balancing"]),
    ("Monitoring & Observability", "DevOps", ["prometheus", "grafana", "datadog", "new relic", "splunk", "observability", "opentelemetry", "application monitoring", "infrastructure monitoring"]),
    ("Kafka", "Data Engineering", ["kafka", "apache kafka", "kinesis", "pub/sub", "pubsub"]),
    ("RabbitMQ", "Backend", ["rabbitmq", "message queue", "message queues", "sqs", "celery"]),
    ("Serverless", "Cloud", ["serverless", "cloud functions"]),
    ("Site Reliability Engineering", "DevOps", ["site reliability", "sre", "incident management", "on-call", "slo", "sla"]),

    # --- Security ---
    ("Cybersecurity", "Security", ["cybersecurity", "cyber security", "information security", "infosec"]),
    ("Network Security", "Security", ["network security", "firewall", "firewalls", "ids/ips", "vpn"]),
    ("Penetration Testing", "Security", ["penetration testing", "pentesting", "pen testing", "vapt", "ethical hacking", "burp suite", "metasploit"]),
    ("SIEM", "Security", ["siem", "soc", "security operations", "qradar", "sentinel"]),
    ("IAM", "Security", ["iam", "identity and access management", "oauth", "oauth2", "sso", "saml", "okta"]),
    ("OWASP", "Security", ["owasp", "application security", "appsec", "secure coding"]),
    ("Cryptography", "Security", ["cryptography", "encryption", "pki"]),

    # --- Data / analytics ---
    ("Excel", "Analytics", ["re:(?<![A-Za-z])(?:Excel|EXCEL)(?![A-Za-z])", "ms excel", "microsoft excel", "advanced excel", "vlookup", "pivot tables", "pivot table", "spreadsheets", "google sheets"]),
    ("Power BI", "Analytics", ["power bi", "powerbi", "dax"]),
    ("Tableau", "Analytics", ["tableau"]),
    ("Looker", "Analytics", ["looker", "looker studio", "data studio"]),
    ("Data Analysis", "Analytics", ["data analysis", "data analytics", "analytical skills", "exploratory data analysis", "eda"]),
    ("Data Visualization", "Analytics", ["data visualization", "data visualisation", "dashboards", "dashboarding", "matplotlib", "seaborn", "plotly", "d3.js"]),
    ("Statistics", "Analytics", ["statistics", "statistical analysis", "hypothesis testing", "regression analysis", "probability", "statistical modeling", "statistical modelling"]),
    ("A/B Testing", "Analytics", ["a/b testing", "a/b test", "ab testing", "experimentation", "split testing"]),
    ("Pandas", "Data", ["pandas"]),
    ("NumPy", "Data", ["numpy"]),
    ("Spark", "Data Engineering", ["spark", "pyspark", "apache spark", "spark sql"]),
    ("Hadoop", "Data Engineering", ["hadoop", "hdfs", "hive", "mapreduce"]),
    ("Airflow", "Data Engineering", ["airflow", "apache airflow", "dagster", "prefect"]),
    ("dbt", "Data Engineering", ["re:(?<![A-Za-z])dbt(?![A-Za-z])", "data build tool"]),
    ("ETL", "Data Engineering", ["etl", "elt", "data pipelines", "data pipeline", "data ingestion"]),
    ("Data Warehousing", "Data Engineering", ["data warehouse", "data warehousing", "snowflake", "redshift", "databricks", "delta lake", "data lake", "lakehouse"]),
    ("Data Modeling", "Data Engineering", ["data modeling", "data modelling", "dimensional modeling", "star schema"]),

    # --- AI / ML ---
    ("Machine Learning", "AI / ML", ["machine learning", "ml models", "ml model", "supervised learning", "unsupervised learning", "predictive modeling", "predictive modelling"]),
    ("Deep Learning", "AI / ML", ["deep learning", "neural networks", "neural network", "cnn", "rnn", "lstm", r"re:(?i)(?<!sentence )(?<!sentence-)(?<![A-Za-z])transformers\b"]),
    ("NLP", "AI / ML", ["nlp", "natural language processing", "text classification", "named entity recognition", "ner", "spacy", "nltk"]),
    ("Computer Vision", "AI / ML", ["computer vision", "image processing", "object detection", "opencv", "yolo", "image classification"]),
    ("Generative AI", "AI / ML", ["generative ai", "genai", "gen ai", "llm", "llms", "large language models", "large language model", "gpt", "prompt engineering", "fine-tuning", "fine tuning", "lora"]),
    ("RAG", "AI / ML", ["rag", "retrieval augmented generation", "retrieval-augmented generation"]),
    ("LangChain", "AI / ML", ["langchain", "llamaindex", "llama index", "langgraph"]),
    ("AI Agents", "AI / ML", ["ai agents", "agentic", "autonomous agents", "multi-agent"]),
    ("PyTorch", "AI / ML", ["pytorch", "torch"]),
    ("TensorFlow", "AI / ML", ["tensorflow", "tf2", "keras"]),
    ("Scikit-learn", "AI / ML", ["scikit-learn", "scikit learn", "sklearn"]),
    ("XGBoost", "AI / ML", ["xgboost", "lightgbm", "catboost", "gradient boosting"]),
    ("Hugging Face", "AI / ML", ["hugging face", "huggingface"]),
    ("MLOps", "AI / ML", ["mlops", "mlflow", "kubeflow", "model deployment", "model serving", "weights & biases", "wandb"]),
    ("Recommendation Systems", "AI / ML", ["recommendation systems", "recommender systems", "recommendation engine", "collaborative filtering"]),
    ("Reinforcement Learning", "AI / ML", ["reinforcement learning", "rlhf"]),
    ("Time Series", "AI / ML", ["time series", "forecasting", "arima"]),
    ("Explainable AI", "AI / ML", ["explainable ai", "xai", "shap", "lime", "model interpretability"]),

    # --- Product / design ---
    ("Product Management", "Product", ["product management", "product manager", "product lifecycle", "product strategy", "product thinking"]),
    ("Product Roadmap", "Product", ["roadmap", "roadmapping", "product roadmap", "prioritization", "rice prioritization", "moscow"]),
    ("PRDs", "Product", ["prd", "prds", "product requirements", "requirement documents", "brd", "functional specifications"]),
    ("User Research", "Product", ["user research", "customer interviews", "user interviews", "usability testing", "customer discovery", "product discovery"]),
    ("Product Analytics", "Product", ["product analytics", "mixpanel", "amplitude", "google analytics", "funnel analysis", "cohort analysis", "retention analysis"]),
    ("Go-to-Market", "Product", ["go-to-market", "go to market", "gtm", "product launch"]),
    ("KPIs & Metrics", "Product", ["kpi", "kpis", "okr", "okrs", "north star metric", "success metrics"]),
    ("Agile", "Product", ["agile", "scrum", "kanban", "sprint planning", "jira", "confluence"]),
    ("Stakeholder Management", "Product", ["stakeholder management", "stakeholder communication", "cross-functional", "cross functional"]),
    ("Figma", "Design", ["figma", "figjam"]),
    ("UI Design", "Design", ["ui design", "user interface", "visual design", "interaction design", "design systems", "design system"]),
    ("UX Design", "Design", ["ux design", "user experience", "ux research", "wireframing", "wireframes", "prototyping", "information architecture"]),
    ("Adobe Creative Suite", "Design", ["photoshop", "illustrator", "adobe xd", "after effects", "premiere pro", "indesign", "adobe creative"]),
    ("Sketch", "Design", ["re:(?<![A-Za-z])Sketch(?![A-Za-z])"]),

    # --- Business / finance / marketing / ops ---
    ("Financial Modeling", "Finance", ["financial modeling", "financial modelling", "dcf", "valuation", "financial analysis"]),
    ("Accounting", "Finance", ["accounting", "bookkeeping", "gaap", "ind as", "ifrs", "accounts payable", "accounts receivable", "bank reconciliation", "general ledger"]),
    ("Taxation", "Finance", ["taxation", "gst", "income tax", "tds", "direct tax", "indirect tax"]),
    ("Audit", "Finance", ["audit", "internal audit", "statutory audit", "sox", "internal controls"]),
    ("Tally", "Finance", ["tally", "tally erp", "tally prime"]),
    ("SAP", "Enterprise", ["re:(?<![A-Za-z])SAP(?![A-Za-z])", "sap fico", "sap mm", "sap sd", "s/4hana", "sap hana"]),
    ("Salesforce CRM", "Enterprise", ["salesforce crm", "salesforce", "sfdc", "crm"]),
    ("ERP", "Enterprise", ["erp", "oracle erp", "netsuite", "odoo"]),
    ("Risk Management", "Finance", ["risk management", "credit risk", "market risk", "risk analysis", "kyc", "aml", "compliance"]),
    ("Digital Marketing", "Marketing", ["digital marketing", "performance marketing", "growth marketing", "paid ads", "google ads", "meta ads", "facebook ads", "sem", "ppc"]),
    ("SEO", "Marketing", ["re:(?<![A-Za-z])SEO(?![A-Za-z])", "search engine optimization", "search engine optimisation"]),
    ("Content Marketing", "Marketing", ["content marketing", "content writing", "copywriting", "content strategy", "social media marketing"]),
    ("Marketing Analytics", "Marketing", ["marketing analytics", "attribution", "campaign analytics", "marketing automation", "hubspot"]),
    ("Brand Management", "Marketing", ["brand management", "branding", "brand strategy"]),
    ("Sales", "Business", ["b2b sales", "b2c sales", "inside sales", "field sales", "enterprise sales", "sales strategy", "sales operations",
                           "pre-sales", "presales", "business development", "lead generation", "account management", "key account management"]),
    ("Customer Success", "Business", ["customer success", "customer support", "customer service", "client relations", "client servicing"]),
    ("Business Analysis", "Business", ["business analysis", "business analyst", "requirements gathering", "process mapping", "gap analysis"]),
    ("Project Management", "Business", ["project management", "program management", "pmp", "prince2", "project planning"]),
    ("Operations", "Business", ["operations management", "business operations", "process improvement", "lean six sigma", "six sigma"]),
    ("Supply Chain", "Business", ["supply chain", "logistics", "procurement", "inventory management", "vendor management", "sourcing"]),
    ("Consulting", "Business", ["consulting", "management consulting", "strategy consulting"]),
    ("Strategy", "Business", ["business strategy", "strategic planning", "market research", "competitive analysis", "market sizing"]),
    ("Recruitment", "HR", ["recruitment", "talent acquisition", "sourcing candidates", "employee onboarding"]),
    ("HR Operations", "HR", ["hr operations", "payroll", "hris", "employee relations", "performance management", "compensation and benefits"]),

    # --- Hardware / embedded ---
    ("Embedded Systems", "Hardware", ["embedded systems", "embedded software", "firmware", "microcontrollers", "microcontroller", "arduino", "raspberry pi", "rtos", "stm32"]),
    ("VLSI", "Hardware", ["vlsi", "asic", "fpga", "rtl design", "physical design", "design verification", "uvm"]),
    ("IoT", "Hardware", ["iot", "internet of things", "mqtt"]),
    ("AutoCAD", "Hardware", ["autocad", "solidworks", "catia", "ansys", "cad"]),

    # --- Soft skills (tracked separately; ATS recruiters rarely search on these) ---
    ("Communication", "Soft Skills", ["communication skills", "communication", "verbal communication", "written communication", "presentation skills"]),
    ("Leadership", "Soft Skills", ["leadership", "team lead", "led a team", "mentoring", "mentorship", "people management"]),
    ("Teamwork", "Soft Skills", ["teamwork", "team player", "collaboration", "collaborative"]),
    ("Problem Solving", "Soft Skills", ["problem-solving", "critical thinking", "analytical thinking"]),
    ("Ownership", "Soft Skills", ["ownership", "self-starter", "bias for action", "accountability"]),
]

SOFT_CATEGORY = "Soft Skills"


def _compile_alias(alias: str) -> re.Pattern:
    if alias.startswith("re:"):
        return re.compile(alias[3:], re.MULTILINE)
    escaped = re.escape(alias).replace(r"\ ", r"[\s\-]?")
    return re.compile(r"(?<![A-Za-z0-9+#.])" + escaped + r"(?![A-Za-z0-9+#])", re.IGNORECASE)


def _count(pats: List[re.Pattern], text: str) -> int:
    """Mentions counted once per position, so 'React.js' isn't counted for both 'react' and 'react.js'."""
    starts = set()
    for p in pats:
        for m in p.finditer(text):
            starts.add(m.start())
    return len(starts)


@lru_cache(maxsize=1)
def _compiled() -> List[Tuple[str, str, List[re.Pattern]]]:
    out = []
    for canonical, category, aliases in _SKILLS:
        pats = [_compile_alias(a) for a in aliases]
        if not any(a.lower() == canonical.lower() for a in aliases if not a.startswith("re:")):
            if not any(a.startswith("re:") for a in aliases):
                pats.append(_compile_alias(canonical))
        out.append((canonical, category, pats))
    return out


def skill_category(canonical: str) -> str:
    for c, cat, _ in _SKILLS:
        if c == canonical:
            return cat
    return "Other"


def find_skills(text: str) -> Dict[str, int]:
    """Canonical skill -> number of mentions in the text."""
    found: Dict[str, int] = {}
    if not text:
        return found
    for canonical, _, pats in _compiled():
        hits = _count(pats, text)
        if hits:
            found[canonical] = hits
    return found


def canonicalize(term: str) -> str:
    """Maps a free-text skill (e.g. from an LLM) to its canonical name, if known."""
    t = (term or "").strip()
    if not t:
        return t
    for canonical, _, pats in _compiled():
        if canonical.lower() == t.lower():
            return canonical
        for p in pats:
            m = p.search(t)
            if m and len(m.group(0)) >= max(1, len(t) - 3):
                return canonical
    return t


def term_in_text(term: str, text: str) -> int:
    """Counts mentions of an arbitrary term in text, alias-aware for known skills.
    Unknown multi-word terms also count when all their significant words appear
    close together, which is roughly how recruiter keyword search behaves."""
    canonical = canonicalize(term)
    for c, _, pats in _compiled():
        if c == canonical:
            return _count(pats, text)
    hits = _count([_compile_alias(term)], text)
    if hits:
        return hits
    words = [w for w in re.findall(r"[a-z0-9+#.]+", term.lower()) if len(w) > 2 and w not in _STOP]
    if len(words) >= 2:
        lower = text.lower()
        window = r"\W+(?:\w+\W+){0,4}?"
        pattern = window.join(re.escape(w) + r"\w*" for w in words)
        return len(re.findall(pattern, lower))
    if len(words) == 1:
        return len(re.findall(r"(?<![a-z0-9])" + re.escape(words[0]) + r"(?:s|es|ing|ed)?(?![a-z0-9])", text.lower()))
    return 0


_STOP = {"and", "the", "with", "for", "of", "in", "on", "to", "a", "an", "or", "using", "experience", "knowledge", "strong", "skills", "skill", "ability", "working", "good", "understanding", "hands", "proficiency"}
