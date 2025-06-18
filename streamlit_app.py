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
import fitz  # PyMuPDF

# Load environment variables
load_dotenv()

# Set the title and favicon that appear in the Browser's tab bar.
st.set_page_config(
    page_title='Lesson Analysis',
    page_icon=':books:', # This is an emoji shortcode
    layout="wide"
)

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
            Please analyze the following combination of lessons based on the provided math standards.
            
            Provide a comprehensive analysis including:
            1. How well the lessons addresses the specified standards
            2. Alignment with the provided standard
            3. Strengths of the lessons
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

    
    prompt = f"""
    {instructions}
    
    MATH STANDARDS:
    {standards}
    
    
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
    """Display the PDF from the given file path with better error handling."""
    try:
        # Reprocess the PDF to ensure compatibility
        processed_path = reprocess_pdf(file_path)
        if not processed_path:
            return

        # Read the reprocessed PDF file and encode it in base64
        with open(processed_path, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')

        # Embed the PDF in an iframe
        pdf_display = f"""
            <iframe
                src="data:application/pdf;base64,{base64_pdf}"
                width="100%"
                height="600px"
                frameborder="0"
            ></iframe>
        """
        st.markdown(pdf_display, unsafe_allow_html=True)
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
def reprocess_pdf(file_path):
    """Reprocess the PDF to ensure compatibility."""
    try:
        doc = fitz.open(file_path)
        output_path = file_path.replace(".pdf", "_processed.pdf")
        doc.save(output_path)
        doc.close()
        return output_path
    except Exception as e:
        st.error(f"Error reprocessing PDF: {e}")
        return None
# -----------------------------------------------------------------------------
# Streamlit UI

st.title('📚 Math Lesson Analysis Tool')

st.markdown("""
This tool analyzes math lessons based on standards.
Select a lesson and standards to get detailed feedback.
""")

# Get lessons organized by grade and unit
lessons_by_grade_and_unit = get_lessons_by_grade_and_unit()

# Sidebar for inputs
with st.sidebar:
    st.header("Lesson Selection")
    
    # Flatten the lessons structure for multi-selection
    all_lessons = []
    for grade, units in lessons_by_grade_and_unit.items():
        for unit, lessons in units.items():
            for lesson in lessons:
                all_lessons.append({
                    "grade": grade,
                    "unit": unit,
                    "name": lesson["name"],
                    "path": lesson["path"],
                    "full_name": lesson["full_name"]
                })
    
    # Create a display name for each lesson
    lesson_options = [
        f"{lesson['grade']} - {lesson['unit']} - {lesson['name']} ({lesson['full_name']})"
        for lesson in all_lessons
    ]
    
    # Multi-selection for lessons
    selected_lesson_display_names = st.multiselect("Select Lessons", lesson_options)
    
    # Get the paths of the selected lessons
    selected_lesson_paths = [
        lesson["path"] for lesson in all_lessons
        if f"{lesson['grade']} - {lesson['unit']} - {lesson['name']} ({lesson['full_name']})" in selected_lesson_display_names
    ]
    
    st.header("Standards Input")
    
    # Replace the dropdown with a text area for user input
    user_provided_standards = st.text_area(
        "Enter math standards for analysis (one standard per line):",
        placeholder="Example:\n1. Standard ID: Description\n2. Standard ID: Description"
    )
    
    # Add some space before the generate button
    st.markdown("---")
    
    # Generate Analysis button
    generate_analysis = st.button("Generate Analysis", type="primary", use_container_width=True)

# Main content area - only run when "Generate Analysis" is clicked
if generate_analysis:
    if selected_lesson_paths:
        # Combine text from all selected lessons
        combined_lesson_text = ""
        for lesson_path in selected_lesson_paths:
            lesson_text = extract_text_from_pdf(lesson_path)
            if lesson_text:
                combined_lesson_text += lesson_text + "\n\n"  # Add spacing between lessons
            else:
                st.error(f"Could not extract text from the PDF: {lesson_path}")

        # Display the combined lesson information
        st.subheader("Selected Lessons")
        for lesson_path in selected_lesson_paths:
            selected_lesson = next(
                (lesson for lesson in all_lessons if lesson["path"] == lesson_path),
                None
            )
            lesson_display_name = f"{selected_lesson['grade']} - {selected_lesson['unit']} - {selected_lesson['name']} ({selected_lesson['full_name']})" if selected_lesson else f"Lesson: {os.path.basename(lesson_path)}"
            st.markdown(f"- {lesson_display_name}")

        # Analyze the combined lesson text
        st.subheader("Analysis Results")
        if user_provided_standards.strip() and combined_lesson_text.strip():
            with st.spinner("Analyzing combined lessons... This may take a moment."):
                analysis = analyze_lesson(user_provided_standards, combined_lesson_text)
                if analysis:
                    st.markdown(analysis)
                else:
                    st.error("Analysis failed. Please check your API key and inputs.")
        else:
            if not user_provided_standards.strip():
                st.error("Please input at least one math standard.")
            else:
                st.error("Could not analyze the selected lessons.")

        # Display PDFs in tabs
        if selected_lesson_paths:
            st.subheader("Selected Lesson PDFs")
            tabs = st.tabs([os.path.basename(path) for path in selected_lesson_paths])
            for tab, lesson_path in zip(tabs, selected_lesson_paths):
                with tab:
                    st.markdown(f"### {os.path.basename(lesson_path)}")
                    display_pdf(lesson_path)
    else:
        st.info("Please select at least one lesson to begin analysis.")

# Footer
st.markdown("---")
st.markdown("Built with Streamlit and Google Gemini API")
