import streamlit as st
import pandas as pd
import os
from pathlib import Path
from dotenv import load_dotenv
import base64
from google import genai
from google.genai import types
import PyPDF2
import docx
from io import BytesIO
# Import the standards dictionary
from math_standards import MATH_STANDARDS

# Load environment variables
load_dotenv()

# Set the title and favicon that appear in the Browser's tab bar.
st.set_page_config(
    page_title='Lesson Analysis',
    page_icon=':books:', # This is an emoji shortcode
    layout="wide"
)

# Map standard domains to their progression document paths
PROGRESSION_DOCS = {
    "MA.6.NSO": "data/6-8 NSO Progression.docx",
    "MA.6.AR": "data/6-8 AR Progression.docx",
    "MA.6.GR": "data/6-8 GR Progression.docx",
    "MA.6.DP": "data/6-8 DP Progression.docx"
}

# -----------------------------------------------------------------------------
# Helper functions for API and PDF handling

def get_api_key():
    """Get Google API key from environment variables."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        st.error("Google API key not found! Please make sure your .env file contains the GOOGLE_API_KEY")
    return api_key

def extract_text_from_pdf(pdf_file):
    """Extract text content from uploaded PDF file."""
    if pdf_file is not None:
        try:
            pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_file.getvalue()))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            st.error(f"Error reading PDF: {e}")
            return None
    return None

def get_required_progression_docs(selected_standards):
    """Determine which progression documents to load based on selected standards."""
    required_docs = set()
    
    for standard_id in selected_standards:
        # Extract the domain prefix (e.g., "MA.6.NSO" from "MA.6.NSO.1.1")
        parts = standard_id.split('.')
        if len(parts) >= 3:
            domain_prefix = '.'.join(parts[:3])
            if domain_prefix in PROGRESSION_DOCS:
                required_docs.add(PROGRESSION_DOCS[domain_prefix])
    
    return list(required_docs)

def load_progression_document(doc_path):
    """Load content from a progression document."""
    try:
        if doc_path.endswith('.docx'):
            # Load DOCX file
            doc = docx.Document(doc_path)
            return '\n'.join([para.text for para in doc.paragraphs])
        elif doc_path.endswith('.pdf'):
            # Load PDF file
            with open(doc_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
        elif doc_path.endswith('.txt'):
            # Load TXT file
            with open(doc_path, 'r', encoding='utf-8') as file:
                return file.read()
    except Exception as e:
        st.warning(f"Error loading {doc_path}: {e}")
        return f"Error loading document: {e}"
    
    return ""

def load_instructions():
    """Load instructions from instructions.txt file."""
    try:
        instructions_path = Path(__file__).parent / "instructions.txt"
        if instructions_path.exists():
            with open(instructions_path, "r", encoding="utf-8") as f:
                return f.read()
        else:
            st.warning("instructions.txt not found. Using default instructions.")
            return """
            Please analyze the following lesson based on the provided math standards and progression document.
            
            Provide a comprehensive analysis including:
            1. How well the lesson addresses the specified standards
            2. Alignment with the progression document
            3. Strengths of the lesson
            4. Areas for improvement
            5. Suggested modifications or extensions
            """
    except Exception as e:
        st.error(f"Error loading instructions: {e}")
        return None

def format_standard_for_display(standard_id):
    """Format a standard for the dropdown display."""
    standard = MATH_STANDARDS[standard_id]
    return f"{standard_id}: {standard['description'][:80]}..." if len(standard['description']) > 80 else f"{standard_id}: {standard['description']}"

def format_standard_for_analysis(standard_id):
    """Format a complete standard with all details for analysis."""
    standard = MATH_STANDARDS[standard_id]
    formatted = f"{standard_id}: {standard['description']}\n"
    
    if standard['clarifications']:
        formatted += "Clarifications:\n"
        for i, clarification in enumerate(standard['clarifications'], 1):
            formatted += f"  {i}. {clarification}\n"
    
    if standard['examples']:
        formatted += "Examples:\n"
        for i, example in enumerate(standard['examples'], 1):
            formatted += f"  {i}. {example}\n"
    
    return formatted + "\n"

def analyze_lesson(standards, lesson_text, user_progression_text=None):
    """Send lesson information to Gemini API for analysis."""
    api_key = get_api_key()
    if not api_key:
        return None
    
    client = genai.Client(api_key=api_key)
    model = "gemini-2.5-flash-preview-05-20"
    
    # Load instructions from file
    instructions = load_instructions()
    if not instructions:
        return None
    
    # Get list of selected standard IDs
    selected_standards = []
    for line in standards.split('\n'):
        if line and ':' in line:
            standard_id = line.split(':')[0].strip()
            selected_standards.append(standard_id)
    
    # Get and load required progression documents
    required_docs = get_required_progression_docs(selected_standards)
    
    # Combine progression documents and user-uploaded content
    progression_text = ""
    
    # Add content from automatically loaded progression documents
    for doc_path in required_docs:
        doc_name = os.path.basename(doc_path)
        content = load_progression_document(doc_path)
        if content:
            progression_text += f"\n--- {doc_name} ---\n"
            # Limit each document to 1000 characters for brevity
            progression_text += content[:1000] + "...\n"
    
    # Add user-uploaded progression document if provided
    if user_progression_text:
        progression_text += "\n--- User Uploaded Progression Document ---\n"
        progression_text += user_progression_text[:1000] + "...\n"
    
    # If no progression documents were found or loaded
    if not progression_text:
        progression_text = "No progression documents available."
    
    prompt = f"""
    {instructions}
    
    MATH STANDARDS:
    {standards}
    
    PROGRESSION DOCUMENTS:
    {progression_text}
    
    LESSON:
    {lesson_text[:3000]}... (truncated for brevity)
    """
    
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        ),
    ]
    
    response = client.models.generate_content(
        model=model,
        contents=contents,
        generation_config={"max_output_tokens": 2048},
    )
    
    return response.text

# -----------------------------------------------------------------------------
# Streamlit UI

st.title('📚 Math Lesson Analysis Tool')

st.markdown("""
This tool analyzes math lessons based on standards and progression documents.
Upload your files and select standards to get detailed feedback on your lesson.
""")

# Sidebar for inputs
with st.sidebar:
    st.header("Lesson Inputs")
    
    # Math Standards Multi-select Dropdown
    st.subheader("Math Standards")
    
    # Create sorted list of standard IDs
    standard_options = sorted(list(MATH_STANDARDS.keys()))
    
    # Create multiselect dropdown for standards
    selected_standards = st.multiselect(
        "Select standards for analysis:",
        options=standard_options,
        format_func=format_standard_for_display
    )
    
    # Display which progression documents will be used
    if selected_standards:
        required_docs = get_required_progression_docs(selected_standards)
        if required_docs:
            st.subheader("Progression Documents")
            for doc_path in required_docs:
                doc_name = os.path.basename(doc_path)
                st.write(f"✓ {doc_name}")
    
    # Format selected standards as text for analysis
    standards_formatted = ""
    if selected_standards:
        for std_id in selected_standards:
            standards_formatted += format_standard_for_analysis(std_id)
    
    # File uploads
    st.subheader("Upload Files")
    
    lesson_pdf = st.file_uploader("Upload Lesson PDF", type="pdf")
    progression_doc = st.file_uploader("Upload Additional Progression Document (Optional)", 
                                      type=["pdf", "docx", "txt"],
                                      help="Upload your own progression document in addition to the standard ones")

# Main content area
if lesson_pdf is not None:
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Lesson PDF")
        lesson_text = extract_text_from_pdf(lesson_pdf)
        if lesson_text:
            st.text_area("Extracted Text Preview", lesson_text[:500] + "...", height=300, disabled=True)
        else:
            st.error("Could not extract text from the PDF.")
    
    with col2:
        st.subheader("Additional Progression Document")
        user_progression_text = ""
        if progression_doc is not None:
            if progression_doc.type == "application/pdf":
                user_progression_text = extract_text_from_pdf(progression_doc)
                if user_progression_text:
                    st.text_area("Document Preview", user_progression_text[:500] + "...", height=300, disabled=True)
                else:
                    st.error("Could not extract text from the document.")
            elif progression_doc.type == "text/plain":
                user_progression_text = progression_doc.getvalue().decode("utf-8")
                st.text_area("Document Preview", user_progression_text[:500] + "...", height=300, disabled=True)
            elif "docx" in progression_doc.type:
                try:
                    doc = docx.Document(BytesIO(progression_doc.getvalue()))
                    user_progression_text = '\n'.join([para.text for para in doc.paragraphs])
                    st.text_area("Document Preview", user_progression_text[:500] + "...", height=300, disabled=True)
                except Exception as e:
                    st.error(f"Error reading DOCX: {e}")
            else:
                st.error("Unsupported file format.")

    # Analysis section
    st.header("Lesson Analysis", divider="gray")
    
    if st.button("Generate Analysis", type="primary", use_container_width=True):
        if selected_standards and lesson_text:
            with st.spinner("Analyzing lesson... This may take a moment."):
                analysis = analyze_lesson(standards_formatted, lesson_text, user_progression_text)
                if analysis:
                    st.markdown(analysis)
                else:
                    st.error("Analysis failed. Please check your API key and inputs.")
        else:
            if not selected_standards:
                st.error("Please select at least one math standard.")
            else:
                st.error("Please upload a lesson PDF.")
else:
    st.info("Please upload a lesson PDF to begin analysis.")

# Footer
st.markdown("---")
st.markdown("Built with Streamlit and Google Gemini API")
