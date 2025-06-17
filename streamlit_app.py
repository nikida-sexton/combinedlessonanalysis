import streamlit as st
import pandas as pd
import os
from pathlib import Path
from dotenv import load_dotenv
import base64
import google.generativeai as genai
import PyPDF2
import docx
from io import BytesIO
import re
import streamlit.components.v1 as components
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

def extract_text_from_pdf(file_path):
    """Extract text content from PDF file at given path."""
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
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
    # Return only the standard ID without the description
    return standard_id

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

def analyze_lesson(standards, lesson_text):
    """Send lesson information to Gemini API for analysis."""
    api_key = get_api_key()
    if not api_key:
        return None
    
    # Initialize the Gemini API
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash-preview-05-20")
    
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
    
    # Combine progression documents content
    progression_text = ""
    
    # Add content from automatically loaded progression documents
    for doc_path in required_docs:
        doc_name = os.path.basename(doc_path)
        content = load_progression_document(doc_path)
        if content:
            progression_text += f"\n--- {doc_name} ---\n"
            progression_text += content + "...\n"
    
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
    {lesson_text}... (truncated for brevity)
    """
    
    # Use the simplified API call with proper generation config
    try:
        generation_config = genai.GenerationConfig(max_output_tokens=8192)
        response = model.generate_content(prompt, generation_config=generation_config)
        return response.text
    except Exception as e:
        st.error(f"API Error: {str(e)}")
        return None

def display_pdf(file_path):
    """Display the PDF from the given file path with better refresh handling."""
    try:
        # Generate a timestamp to ensure unique rendering each time
        timestamp = str(os.path.getmtime(file_path))
        
        with open(file_path, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        
        # Create a container for the PDF display
        pdf_container = st.empty()
        
        # Embed PDF viewer HTML with multiple cache-busting techniques
        pdf_display = f"""
            <div style="width:100%; height:600px;">
                <iframe
                    src="data:application/pdf;base64,{base64_pdf}#{timestamp}"
                    width="100%"
                    height="100%"
                    type="application/pdf"
                    frameborder="0"
                    scrolling="auto"
                ></iframe>
            </div>
        """
        
        # Use the container to update the HTML
        pdf_container.markdown(pdf_display, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Error displaying PDF: {e}")

def get_lessons_by_grade_and_unit():
    """Scan the lessons directory and organize PDFs by grade and unit."""
    lessons_dir = Path(__file__).parent / "lessons"
    if not lessons_dir.exists():
        st.error(f"Lessons directory not found at {lessons_dir}")
        return {}
    
    # Dictionary to store lessons by grade and unit
    lessons_by_grade_and_unit = {}
    
    # Regular expression to match lesson file patterns like "6.02.06.pdf"
    pattern = re.compile(r"(\d+)\.(\d+)\.(\d+)\.pdf")
    
    # Scan directory for PDF files
    for file_path in lessons_dir.glob("*.pdf"):
        file_name = file_path.name
        match = pattern.match(file_name)
        
        if match:
            grade, unit, lesson = match.groups()
            grade_key = f"Grade {int(grade)}"  # Convert "6" to "Grade 6"
            unit_key = f"Unit {int(unit)}"    # Convert "02" to "Unit 2"
            lesson_number = int(lesson)      # Convert "06" to 6
            
            # Create simplified lesson name for display
            lesson_name = f"Lesson {lesson_number}"
            
            # Add to dictionary
            if grade_key not in lessons_by_grade_and_unit:
                lessons_by_grade_and_unit[grade_key] = {}
            if unit_key not in lessons_by_grade_and_unit[grade_key]:
                lessons_by_grade_and_unit[grade_key][unit_key] = []
            
            lessons_by_grade_and_unit[grade_key][unit_key].append({
                "name": lesson_name,
                "path": str(file_path),
                "number": lesson_number,    # Store lesson number for sorting
                "full_name": file_name      # Keep original filename for reference
            })
    
    # Sort grades, units, and lessons by numerical order
    return {
        grade: {
            unit: sorted(lessons, key=lambda x: x["number"])
            for unit, lessons in sorted(units.items())
        }
        for grade, units in sorted(lessons_by_grade_and_unit.items())
    }
# -----------------------------------------------------------------------------
# Streamlit UI

st.title('📚 Math Lesson Analysis Tool')

st.markdown("""
This tool analyzes math lessons based on standards and progression documents.
Select a lesson and standards to get detailed feedback.
""")

# Get lessons organized by grade and unit
lessons_by_grade_and_unit = get_lessons_by_grade_and_unit()

# Sidebar for inputs
with st.sidebar:
    st.header("Lesson Selection")
    
    # Grade selection
    grades = list(lessons_by_grade_and_unit.keys())
    if grades:
        selected_grade = st.selectbox("Select Grade", grades)
        
        # Unit selection within the selected grade
        units = list(lessons_by_grade_and_unit[selected_grade].keys())
        if units:
            selected_unit = st.selectbox("Select Unit", units)
            
            # Lesson selection within the selected unit
            lessons = lessons_by_grade_and_unit[selected_grade][selected_unit]
            lesson_options = [lesson["name"] for lesson in lessons]
            selected_lesson_name = st.selectbox("Select Lesson", lesson_options)
            
            # Get the selected lesson path
            selected_lesson_path = next(
                (lesson["path"] for lesson in lessons if lesson["name"] == selected_lesson_name),
                None
            )
        else:
            st.error("No units found for the selected grade.")
            selected_lesson_path = None
    else:
        st.error("No lessons found in the lessons directory.")
        selected_lesson_path = None
    
    st.header("Standards Selection")
    
    # Math Standards Multi-select Dropdown
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
    
    # Add some space before the generate button
    st.markdown("---")
    
    # Generate Analysis button
    generate_analysis = st.button("Generate Analysis", type="primary", use_container_width=True)

# Main content area - create two columns
if selected_lesson_path:
    # Create two columns for the main content area
    col1, col2 = st.columns(2)
    
    # Extract text for analysis (but don't show it)
    lesson_text = extract_text_from_pdf(selected_lesson_path)
    if not lesson_text:
        with col1:
            st.error("Could not extract text from the PDF for analysis.")
    
    # Get selected lesson info for display
    selected_lesson = next(
        (lesson for lesson in lessons_by_grade_and_unit[selected_grade][selected_unit] if lesson["path"] == selected_lesson_path),
        None
    )
    lesson_display_name = f"{selected_lesson['name']} ({selected_lesson['full_name']})" if selected_lesson else f"Lesson: {os.path.basename(selected_lesson_path)}"
    
    with col1:
        # Left column: Display the PDF document immediately
        st.subheader(f"{selected_grade} - {selected_unit} - {lesson_display_name}")
        display_pdf(selected_lesson_path)
    
    with col2:
        # Right column: Display analysis results
        st.subheader("Analysis Results")
        
        # If the generate button was clicked
        if generate_analysis:
            if selected_standards and lesson_text:
                # Show the analysis
                with st.spinner("Analyzing lesson... This may take a moment."):
                    analysis = analyze_lesson(standards_formatted, lesson_text)
                    if analysis:
                        st.markdown(analysis)
                    else:
                        st.error("Analysis failed. Please check your API key and inputs.")
            else:
                if not selected_standards:
                    st.error("Please select at least one math standard.")
                else:
                    st.error("Could not analyze the selected lesson.")
        else:
            st.info("Click 'Generate Analysis' in the sidebar to analyze the lesson based on selected standards.")
else:
    st.info("Please select a grade, unit, and lesson to begin analysis.")

# Footer
st.markdown("---")
st.markdown("Built with Streamlit and Google Gemini API")
