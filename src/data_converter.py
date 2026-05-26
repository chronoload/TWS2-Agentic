
"""
Data Format Converter Module
Supports JSON <-> CSV <-> XLSX bidirectional conversion
"""
import json
from pathlib import Path


def json_to_csv(json_path, csv_path=None):
    """
    Convert structured course JSON to CSV format
    CSV contains course and lesson information
    
    Args:
        json_path: Input JSON file path
        csv_path: Output CSV file path (optional)
    
    Returns:
        Output file path
    """
    import pandas as pd
    
    json_path = Path(json_path)
    if not csv_path:
        csv_path = json_path.with_suffix('.csv')
    else:
        csv_path = Path(csv_path)
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Flatten data structure
    flat_rows = []
    
    for course in data.get('courses', []):
        # Basic course info
        course_info = {
            'note_id': course.get('note_id', ''),
            'course_title': course.get('course_title', ''),
            'total_hours': course.get('total_hours', 0),
            'filename': course.get('filename', ''),
            'prerequisites': '; '.join(course.get('prerequisites', []))
        }
        
        # Section info
        sections = course.get('sections', [])
        section_map = {}
        for sec in sections:
            section_map[sec.get('section_number', 0)] = {
                'section_title': sec.get('section_title', ''),
                'section_hours': sec.get('section_hours', 0),
                'lesson_range': sec.get('lesson_range', '')
            }
        
        # Lesson info
        for lesson in course.get('lessons', []):
            sec_num = lesson.get('section', 0)
            section_info = section_map.get(sec_num, {})
            
            row = {
                'note_id': course_info['note_id'],
                'course_title': course_info['course_title'],
                'total_hours': course_info['total_hours'],
                'filename': course_info['filename'],
                'prerequisites': course_info['prerequisites'],
                'section_number': sec_num,
                'section_title': section_info.get('section_title', ''),
                'section_hours': section_info.get('section_hours', 0),
                'lesson_range': section_info.get('lesson_range', ''),
                'lesson_number': lesson.get('lesson_number', 0),
                'lesson_title': lesson.get('lesson_title', ''),
                'central_question': lesson.get('central_question', ''),
                'description': lesson.get('description', ''),
                'references': '; '.join(lesson.get('references', []))
            }
            flat_rows.append(row)
    
    # Write CSV
    df = pd.DataFrame(flat_rows)
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    return csv_path


def json_to_xlsx(json_path, xlsx_path=None):
    """
    Convert structured course JSON to XLSX format
    XLSX contains multiple sheets: course list, section info, lesson details
    
    Args:
        json_path: Input JSON file path
        xlsx_path: Output XLSX file path (optional)
    
    Returns:
        Output file path
    """
    import pandas as pd
    
    json_path = Path(json_path)
    if not xlsx_path:
        xlsx_path = json_path.with_suffix('.xlsx')
    else:
        xlsx_path = Path(xlsx_path)
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Prepare data
    courses_data = []
    sections_data = []
    lessons_data = []
    
    for course in data.get('courses', []):
        course_id = course.get('note_id', '')
        course_title = course.get('course_title', '')
        
        # Basic course info
        courses_data.append({
            'note_id': course_id,
            'course_title': course_title,
            'total_hours': course.get('total_hours', 0),
            'filename': course.get('filename', ''),
            'prerequisites': '; '.join(course.get('prerequisites', [])),
            'lesson_count': len(course.get('lessons', [])),
            'section_count': len(course.get('sections', []))
        })
        
        # Section info
        for sec in course.get('sections', []):
            sections_data.append({
                'note_id': course_id,
                'course_title': course_title,
                'section_number': sec.get('section_number', 0),
                'section_title': sec.get('section_title', ''),
                'section_hours': sec.get('section_hours', 0),
                'lesson_range': sec.get('lesson_range', '')
            })
        
        # Lesson info
        for lesson in course.get('lessons', []):
            lessons_data.append({
                'note_id': course_id,
                'course_title': course_title,
                'section_number': lesson.get('section', 0),
                'lesson_number': lesson.get('lesson_number', 0),
                'lesson_title': lesson.get('lesson_title', ''),
                'central_question': lesson.get('central_question', ''),
                'description': lesson.get('description', ''),
                'references': '; '.join(lesson.get('references', []))
            })
    
    # Write Excel
    with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
        pd.DataFrame(courses_data).to_excel(writer, sheet_name='course_list', index=False)
        pd.DataFrame(sections_data).to_excel(writer, sheet_name='section_info', index=False)
        pd.DataFrame(lessons_data).to_excel(writer, sheet_name='lesson_details', index=False)
    
    return xlsx_path


def csv_to_json(csv_path, json_path=None):
    """
    Convert CSV back to structured course JSON format
    
    Args:
        csv_path: Input CSV file path
        json_path: Output JSON file path (optional)
    
    Returns:
        Output file path
    """
    import pandas as pd
    from collections import defaultdict
    
    csv_path = Path(csv_path)
    if not json_path:
        json_path = csv_path.with_suffix('.json')
    else:
        json_path = Path(json_path)
    
    df = pd.read_csv(csv_path, encoding='utf-8-sig')
    
    # Group by course
    course_map = defaultdict(lambda: {
        'note_id': '',
        'course_title': '',
        'total_hours': 0,
        'filename': '',
        'prerequisites': [],
        'sections': [],
        'lessons': []
    })
    
    for _, row in df.iterrows():
        course_id = str(row.get('note_id', ''))
        
        # Update basic course info (only once)
        if not course_map[course_id]['note_id']:
            course_map[course_id]['note_id'] = course_id
            course_map[course_id]['course_title'] = str(row.get('course_title', ''))
            course_map[course_id]['total_hours'] = int(row.get('total_hours', 0))
            course_map[course_id]['filename'] = str(row.get('filename', ''))
            prereq_str = str(row.get('prerequisites', ''))
            if prereq_str and prereq_str != 'nan':
                course_map[course_id]['prerequisites'] = [p.strip() for p in prereq_str.split(';') if p.strip()]
        
        # Add section (deduplicate)
        sec_num = int(row.get('section_number', 0))
        existing_sections = {s['section_number']: s for s in course_map[course_id]['sections']}
        if sec_num not in existing_sections:
            course_map[course_id]['sections'].append({
                'section_number': sec_num,
                'section_title': str(row.get('section_title', '')),
                'section_hours': int(row.get('section_hours', 0)),
                'lesson_range': str(row.get('lesson_range', ''))
            })
        
        # Add lesson
        ref_str = str(row.get('references', ''))
        references = []
        if ref_str and ref_str != 'nan':
            references = [r.strip() for r in ref_str.split(';') if r.strip()]
        
        course_map[course_id]['lessons'].append({
            'lesson_number': int(row.get('lesson_number', 0)),
            'lesson_title': str(row.get('lesson_title', '')),
            'section': sec_num,
            'description': str(row.get('description', '')),
            'central_question': str(row.get('central_question', '')),
            'references': references
        })
    
    # Build output structure
    output_data = {
        'metadata': {
            'generated_at': '',
            'framework': 'Imported from CSV file'
        },
        'courses': list(course_map.values())
    }
    
    # Sort lessons by number
    for course in output_data['courses']:
        course['lessons'].sort(key=lambda x: x['lesson_number'])
        course['sections'].sort(key=lambda x: x['section_number'])
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    return json_path


def xlsx_to_json(xlsx_path, json_path=None):
    """
    Convert XLSX back to structured course JSON format
    
    Args:
        xlsx_path: Input XLSX file path
        json_path: Output JSON file path (optional)
    
    Returns:
        Output file path
    """
    import pandas as pd
    
    xlsx_path = Path(xlsx_path)
    if not json_path:
        json_path = xlsx_path.with_suffix('.json')
    else:
        json_path = Path(json_path)
    
    # Read all sheets
    try:
        courses_df = pd.read_excel(xlsx_path, sheet_name='course_list')
        sections_df = pd.read_excel(xlsx_path, sheet_name='section_info')
        lessons_df = pd.read_excel(xlsx_path, sheet_name='lesson_details')
    except Exception as e:
        # If specific sheets not found, try to read first sheet
        xls = pd.ExcelFile(xlsx_path)
        sheet_names = xls.sheet_names
        if len(sheet_names) > 0:
            df = pd.read_excel(xlsx_path, sheet_name=0)
            return _simple_xlsx_to_json(df, json_path, xlsx_path.name)
        else:
            raise Exception("Cannot read XLSX file")
    
    # Build course mapping
    courses = []
    
    for _, course_row in courses_df.iterrows():
        course_id = str(course_row.get('note_id', ''))
        course = {
            'note_id': course_id,
            'course_title': str(course_row.get('course_title', '')),
            'total_hours': int(course_row.get('total_hours', 0)),
            'filename': str(course_row.get('filename', '')),
            'prerequisites': [],
            'sections': [],
            'lessons': []
        }
        
        # Parse prerequisites
        prereq_str = str(course_row.get('prerequisites', ''))
        if prereq_str and prereq_str != 'nan':
            course['prerequisites'] = [p.strip() for p in prereq_str.split(';') if p.strip()]
        
        # Add sections
        course_sections = sections_df[sections_df['note_id'] == course_id]
        for _, sec_row in course_sections.iterrows():
            course['sections'].append({
                'section_number': int(sec_row.get('section_number', 0)),
                'section_title': str(sec_row.get('section_title', '')),
                'section_hours': int(sec_row.get('section_hours', 0)),
                'lesson_range': str(sec_row.get('lesson_range', ''))
            })
        
        # Add lessons
        course_lessons = lessons_df[lessons_df['note_id'] == course_id]
        for _, lesson_row in course_lessons.iterrows():
            ref_str = str(lesson_row.get('references', ''))
            references = []
            if ref_str and ref_str != 'nan':
                references = [r.strip() for r in ref_str.split(';') if r.strip()]
            
            course['lessons'].append({
                'lesson_number': int(lesson_row.get('lesson_number', 0)),
                'lesson_title': str(lesson_row.get('lesson_title', '')),
                'section': int(lesson_row.get('section_number', 0)),
                'description': str(lesson_row.get('description', '')),
                'central_question': str(lesson_row.get('central_question', '')),
                'references': references
            })
        
        # Sort lessons by number
        course['lessons'].sort(key=lambda x: x['lesson_number'])
        course['sections'].sort(key=lambda x: x['section_number'])
        
        courses.append(course)
    
    # Build output structure
    output_data = {
        'metadata': {
            'generated_at': '',
            'framework': 'Imported from XLSX file'
        },
        'courses': courses
    }
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    return json_path


def _simple_xlsx_to_json(df, json_path, filename):
    """
    Simple XLSX to JSON conversion (when specific sheets not found)
    """
    import pandas as pd
    from collections import defaultdict
    
    json_path = Path(json_path)
    
    course_map = defaultdict(lambda: {
        'note_id': '',
        'course_title': '',
        'total_hours': 0,
        'filename': '',
        'prerequisites': [],
        'sections': [],
        'lessons': []
    })
    
    for _, row in df.iterrows():
        # Try to get course ID
        course_id = str(row.get('note_id', row.get('course_id', '')))
        if not course_id or course_id == 'nan':
            course_id = str(hash(str(row.get('course_title', ''))))
        
        # Update basic course info
        if not course_map[course_id]['note_id']:
            course_map[course_id]['note_id'] = course_id
            course_map[course_id]['course_title'] = str(row.get('course_title', ''))
            course_map[course_id]['total_hours'] = int(row.get('total_hours', 0))
        
        # Add lesson
        lesson = {
            'lesson_number': int(row.get('lesson_number', len(course_map[course_id]['lessons']) + 1)),
            'lesson_title': str(row.get('lesson_title', '')),
            'section': int(row.get('section_number', 1)),
            'description': str(row.get('description', '')),
            'central_question': str(row.get('central_question', '')),
            'references': []
        }
        ref_str = str(row.get('references', ''))
        if ref_str and ref_str != 'nan':
            lesson['references'] = [r.strip() for r in ref_str.split(';') if r.strip()]
        
        course_map[course_id]['lessons'].append(lesson)
        
        # Add section if not exists
        sec_num = lesson['section']
        existing_sections = {s['section_number']: s for s in course_map[course_id]['sections']}
        if sec_num not in existing_sections:
            course_map[course_id]['sections'].append({
                'section_number': sec_num,
                'section_title': str(row.get('section_title', 'Chapter %d' % sec_num)),
                'section_hours': 0,
                'lesson_range': ''
            })
    
    # Build output
    output_data = {
        'metadata': {
            'generated_at': '',
            'framework': 'Imported from file %s' % filename
        },
        'courses': list(course_map.values())
    }
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    return json_path


def convert_file(input_path, output_format, output_path=None):
    """
    Generic conversion function
    
    Args:
        input_path: Input file path
        output_format: Target format ('json', 'csv', 'xlsx')
        output_path: Output file path (optional)
    
    Returns:
        Output file path
    """
    input_path = Path(input_path)
    input_suffix = input_path.suffix.lower()
    
    if input_suffix == '.json':
        if output_format == 'csv':
            return json_to_csv(input_path, output_path)
        elif output_format == 'xlsx':
            return json_to_xlsx(input_path, output_path)
        else:
            raise ValueError('Unsupported output format: %s' % output_format)
    elif input_suffix == '.csv':
        if output_format == 'json':
            return csv_to_json(input_path, output_path)
        else:
            raise ValueError('From CSV only conversion to JSON is supported')
    elif input_suffix in ['.xlsx', '.xls']:
        if output_format == 'json':
            return xlsx_to_json(input_path, output_path)
        else:
            raise ValueError('From XLSX only conversion to JSON is supported')
    else:
        raise ValueError('Unsupported input format: %s' % input_suffix)


if __name__ == "__main__":
    # Test code
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python data_converter.py <input_file> <output_format> [output_file]")
        print("Output format: json, csv, xlsx")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_format = sys.argv[2].lower()
    output_file = sys.argv[3] if len(sys.argv) > 3 else None
    
    result = convert_file(input_file, output_format, output_file)
    print("Conversion successful: %s" % result)

