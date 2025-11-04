import streamlit as st
import pandas as pd
import os
from reportlab.lib.pagesizes import landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, PageBreak, Image
from reportlab.lib.units import cm, inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.utils import ImageReader
from io import BytesIO
import subprocess
import sys
import re
import tempfile

# Define sticker dimensions
STICKER_WIDTH = 10 * cm
STICKER_HEIGHT = 15 * cm
STICKER_PAGESIZE = (STICKER_WIDTH, STICKER_HEIGHT)

# Define content box dimensions
CONTENT_BOX_WIDTH = 10 * cm  # Same width as page
CONTENT_BOX_HEIGHT = 7.2 * cm  # Half the page height

# Check for PIL and install if needed
try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    st.write("PIL not available. Installing...")
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pillow'])
    from PIL import Image as PILImage
    PIL_AVAILABLE = True

# Check for QR code library and install if needed
try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False
    st.write("qrcode not available. Installing...")
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'qrcode'])
    import qrcode
    QR_AVAILABLE = True

# Define paragraph styles
bold_style = ParagraphStyle(name='Bold', fontName='Helvetica-Bold', fontSize=16, alignment=TA_CENTER, leading=14)
desc_style = ParagraphStyle(name='Description', fontName='Helvetica', fontSize=11, alignment=TA_CENTER, leading=12)
qty_style = ParagraphStyle(name='Quantity', fontName='Helvetica', fontSize=11, alignment=TA_CENTER, leading=12)

def find_bus_model_column(df_columns):
    """
    Enhanced function to find the bus model column with better detection
    """
    cols = [str(col).upper() for col in df_columns]
    
    # Priority order for bus model column detection
    patterns = [
        # Exact matches (highest priority)
        lambda col: col == 'BUS_MODEL',
        lambda col: col == 'BUSMODEL',
        lambda col: col == 'BUS MODEL',
        lambda col: col == 'MODEL',
        lambda col: col == 'BUS_TYPE',
        lambda col: col == 'BUSTYPE',
        lambda col: col == 'BUS TYPE',
        lambda col: col == 'VEHICLE_TYPE',
        lambda col: col == 'VEHICLETYPE',
        lambda col: col == 'VEHICLE TYPE',
        # Partial matches (lower priority)
        lambda col: 'BUS' in col and 'MODEL' in col,
        lambda col: 'BUS' in col and 'TYPE' in col,
        lambda col: 'VEHICLE' in col and 'MODEL' in col,
        lambda col: 'VEHICLE' in col and 'TYPE' in col,
        lambda col: 'MODEL' in col,
        lambda col: 'BUS' in col,
        lambda col: 'VEHICLE' in col,
    ]
    
    for pattern in patterns:
        for i, col in enumerate(cols):
            if pattern(col):
                return df_columns[i]  # Return original column name
    
    return None

def detect_bus_model_and_qty(row, qty_veh_col, bus_model_col=None):
    """
    Improved bus model detection that properly matches bus model to MTM box
    Returns a dictionary with keys '4W', '3WS', '3WM','3WC' and their respective quantities
    """
    # Initialize result dictionary
    result = {'4W': '', '3WS': '', '3WM': '', '3WC': ''}
    
    # Get quantity value
    qty_veh = ""
    if qty_veh_col and qty_veh_col in row and pd.notna(row[qty_veh_col]):
        qty_veh = str(row[qty_veh_col]).strip()
    
    if not qty_veh:
        return result
    
    # Method 1: Check if quantity already contains model info (e.g., "3WS:2", "4W: 3", "3WM: 5", "3WC: 6")
    qty_pattern = r'(\d+W[SMC]?)[:\-\s]*(\d+)'
    matches = re.findall(qty_pattern, qty_veh.upper())
    
    if matches:
        # If we found model-quantity pairs in the qty_veh field itself
        for model, quantity in matches:
            if model in result:
                result[model] = quantity
        return result
    
    # Method 2: Look for bus model in dedicated bus model column first
    detected_model = None
    if bus_model_col and bus_model_col in row and pd.notna(row[bus_model_col]):
        bus_model_value = str(row[bus_model_col]).strip().upper()
        
        # Check for exact matches first
        if bus_model_value in ['4W', '4']:
            detected_model = '4W'
        elif bus_model_value in ['3WS', '3S']:
            detected_model = '3WS'
        elif bus_model_value in ['3WM', '3M']:
            detected_model = '3WM'
        elif bus_model_value in ['3WC', '3C']:
            detected_model = '3WC'
        # Check for patterns within the text
        elif re.search(r'\b4W\b', bus_model_value):
            detected_model = '4W'
        elif re.search(r'\b3WS\b', bus_model_value):
            detected_model = '3WS'
        elif re.search(r'\b3WM\b', bus_model_value):
            detected_model = '3WM'
        elif re.search(r'\b3WC\b', bus_model_value):
            detected_model = '3WC'
        # Check for standalone numbers
        elif re.search(r'\b4\b', bus_model_value):
            detected_model = '4W'
        elif re.search(r'\b3S\b', bus_model_value):
            detected_model = '3WS'
        elif re.search(r'\b3M\b', bus_model_value):
            detected_model = '3WM'
        elif re.search(r'\b3C\b', bus_model_value):
            detected_model = '3WC'
    
    # If we found a model in the dedicated column, use it
    if detected_model:
        result[detected_model] = qty_veh
        return result
    
    # Method 3: Search through all columns systematically with priority
    # First, search in columns that are most likely to contain bus model info
    priority_columns = []
    other_columns = []
    
    for col in row.index:
        if pd.notna(row[col]):
            col_upper = str(col).upper()
            # High priority columns
            if any(keyword in col_upper for keyword in ['MODEL', 'BUS', 'VEHICLE', 'TYPE']):
                priority_columns.append(col)
            else:
                other_columns.append(col)
    
    # Search priority columns first
    for col in priority_columns:
        if pd.notna(row[col]):
            value_str = str(row[col]).upper()
            
            # Look for exact matches first
            if re.search(r'\b4W\b', value_str):
                result['4W'] = qty_veh
                return result
            elif re.search(r'\b3WS\b', value_str):
                result['3WS'] = qty_veh
                return result
            elif re.search(r'\b3WM\b', value_str):
                result['3WM'] = qty_veh
                return result
            elif re.search(r'\b3WC\b', value_str):
                result['3WC'] = qty_veh
                return result
            # Then look for standalone numbers in context
            elif re.search(r'\b4\b', value_str) and any(keyword in value_str for keyword in ['BUS', 'METER', 'M']):
                result['4W'] = qty_veh
                return result
            elif re.search(r'\b3S\b', value_str) and any(keyword in value_str for keyword in ['BUS', 'METER', 'M']):
                result['3WS'] = qty_veh
                return result
            elif re.search(r'\b3M\b', value_str) and any(keyword in value_str for keyword in ['BUS', 'METER', 'M']):
                result['3WM'] = qty_veh
                return result
            elif re.search(r'\b3C\b', value_str) and any(keyword in value_str for keyword in ['BUS', 'METER', 'M']):
                result['3WC'] = qty_veh
                return result
    
    # Method 4: Search in other columns as fallback
    detected_models = []
    for col in other_columns:
        if pd.notna(row[col]):
            value_str = str(row[col]).upper()
            
            # Use word boundaries to avoid false matches
            if re.search(r'\b4W\b', value_str):
                detected_models.append('4W')
            elif re.search(r'\b3WS\b', value_str):
                detected_models.append('3WS')
            elif re.search(r'\b3WM\b', value_str):
                detected_models.append('3WM')
            elif re.search(r'\b3WC\b', value_str):
                detected_models.append('3WC')
    
    # Remove duplicates while preserving order
    detected_models = list(dict.fromkeys(detected_models))
    
    if detected_models:
        # Use the first detected model
        result[detected_models[0]] = qty_veh
        return result
    
    # Method 5: Last resort - look for standalone numbers that might indicate bus length
    for col in row.index:
        if pd.notna(row[col]):
            value_str = str(row[col]).strip()
            
            # Look for exact matches of just the number
            if value_str == '4':
                result['4W'] = qty_veh
                return result
            elif value_str == '3S':
                result['3WS'] = qty_veh
                return result
            elif value_str == '3M':
                result['3WM'] = qty_veh
                return result
            elif value_str == '3C':
                result['3WC'] = qty_veh
                return result
    
    # Method 6: If still no model detected, return empty (no boxes filled)
    return result

def generate_qr_code(data_string):
    """
    Generate a QR code from the given data string
    """
    try:
        # Create QR code instance
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        
        # Add data
        qr.add_data(data_string)
        qr.make(fit=True)
        
        # Create QR code image
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert PIL image to bytes that reportlab can use
        img_buffer = BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        # Create a QR code image with specified size
        return Image(img_buffer, width=2.2*cm, height=2.2*cm)
    except Exception as e:
        st.error(f"Error generating QR code: {e}")
        import traceback
        traceback.print_exc()
        return None

def parse_location_string(location_str):
    """Parse a location string into components for table display"""
    # Initialize with empty values
    location_parts = [''] * 7
    if not location_str or not isinstance(location_str, str):
        return location_parts
    # Remove any extra spaces
    location_str = location_str.strip()
    # Try to parse location components
    import re
    pattern = r'([^_\s]+)'
    matches = re.findall(pattern, location_str)
    # Fill the available parts
    for i, match in enumerate(matches[:7]):
        location_parts[i] = match
    return location_parts

def extract_location_data_from_excel(row_data):
    """Extract location data from Excel row for Line Location"""
    # Get all available columns for debugging
    available_cols = list(row_data.index) if hasattr(row_data, 'index') else []
    
    # Try different variations of column names (case-insensitive)
    def find_column_value(possible_names, default=''):
        for name in possible_names:
            # Try exact match first
            if name in row_data:
                val = row_data[name]
                return str(val) if pd.notna(val) and str(val).lower() != 'nan' else default
            # Try case-insensitive match
            for col in available_cols:
                if isinstance(col, str) and col.upper() == name.upper():
                    val = row_data[col]
                    return str(val) if pd.notna(val) and str(val).lower() != 'nan' else default
        return default
    
    # Extract values with multiple possible column names
    bus_model = find_column_value(['Bus Model', 'Bus model', 'BUS MODEL', 'BUSMODEL', 'Bus_Model'])
    station_no = find_column_value(['Station No', 'Station no', 'STATION NO', 'STATIONNO', 'Station_No'])
    rack = find_column_value(['Rack', 'RACK', 'rack'])
    rack_no_1st = find_column_value(['Rack No (1st digit)', 'RACK NO (1st digit)', 'Rack_No_1st', 'RACK_NO_1ST'])
    rack_no_2nd = find_column_value(['Rack No (2nd digit)', 'RACK NO (2nd digit)', 'Rack_No_2nd', 'RACK_NO_2ND'])
    level = find_column_value(['Level', 'LEVEL', 'level'])
    cell = find_column_value(['Cell', 'CELL', 'cell'])
    
    return [bus_model, station_no, rack, rack_no_1st, rack_no_2nd, level, cell]

def extract_store_location_data_from_excel(row_data):
    """Extract store location data from Excel row for Store Location"""
    def get_clean_value(key, default=''):
        val = row_data.get(key, default)
        if pd.notna(val) and str(val).lower() != 'nan':
            return str(val)
        return default
    
    # Extract ABB values from Excel columns with proper NaN handling
    zone = get_clean_value('ABB ZONE', '')
    location = get_clean_value('ABB LOCATION', '')
    floor = get_clean_value('ABB FLOOR', '')
    rack_no = get_clean_value('ABB RACK NO', '')
    level_in_rack = get_clean_value('ABB LEVEL IN RACK', '')
    cell = get_clean_value('ABB CELL', '')
    no = get_clean_value('ABB NO', '')
    
    return [zone, location, floor, rack_no, level_in_rack, cell, no]
def generate_sticker_labels(excel_file_path, output_pdf_path, status_callback=None):
    """Generate sticker labels with QR code from Excel data"""
    if status_callback:
        status_callback(f"Processing file: {excel_file_path}")
    else:
        st.write(f"Processing file: {excel_file_path}")

    # Create a function to draw the border box around content
    def draw_border(canvas, doc):
        canvas.saveState()
        # Draw border box around the content area (10cm x 7.5cm)
        # Position it at the top of the page with minimal margin
        x_offset = (STICKER_WIDTH - CONTENT_BOX_WIDTH) / 2
        y_offset = STICKER_HEIGHT - CONTENT_BOX_HEIGHT - 0.2*cm  # Position at top with minimal margin
        canvas.setStrokeColor(colors.Color(0, 0, 0, alpha=0.95))  # Slightly darker black (95% opacity)
        canvas.setLineWidth(1.8)  # Slightly thicker border
        canvas.rect(
            x_offset + doc.leftMargin,
            y_offset,
            CONTENT_BOX_WIDTH - 0.2*cm,  # Account for margins
            CONTENT_BOX_HEIGHT
        )
        canvas.restoreState()

    # Load the Excel data
    try:
        if excel_file_path.lower().endswith('.csv'):
            df = pd.read_csv(excel_file_path)
        else:
            try:
                df = pd.read_excel(excel_file_path)
            except Exception as e:
                try:
                    df = pd.read_excel(excel_file_path, engine='openpyxl')
                except Exception as e2:
                    df = pd.read_csv(excel_file_path, encoding='latin1')

        if status_callback:
            status_callback(f"Successfully read file with {len(df)} rows")
            status_callback(f"Columns found: {df.columns.tolist()}")
        else:
            st.write(f"Successfully read file with {len(df)} rows")
            st.write("Columns found:", df.columns.tolist())
    except Exception as e:
        error_msg = f"Error reading file: {e}"
        if status_callback:
            status_callback(error_msg)
        else:
            st.error(error_msg)
        return None

    # Identify columns (case-insensitive)
    original_columns = df.columns.tolist()
    df.columns = [col.upper() if isinstance(col, str) else col for col in df.columns]
    cols = df.columns.tolist()

    # Find relevant columns
    part_no_col = next((col for col in cols if 'PART' in col and ('NO' in col or 'NUM' in col or '#' in col)),
                   next((col for col in cols if col in ['PARTNO', 'PART']), cols[0]))

    desc_col = next((col for col in cols if 'DESC' in col),
                   next((col for col in cols if 'NAME' in col), cols[1] if len(cols) > 1 else part_no_col))

    # Look specifically for "QTY/BIN" column first, then fall back to general QTY column
    qty_bin_col = next((col for col in cols if 'QTY/BIN' in col or 'QTY_BIN' in col or 'QTYBIN' in col), 
                  next((col for col in cols if 'QTY' in col and 'BIN' in col), None))
    
    # If no specific QTY/BIN column is found, fall back to general QTY column
    if not qty_bin_col:
        qty_bin_col = next((col for col in cols if 'QTY' in col),
                      next((col for col in cols if 'QUANTITY' in col), None))
  
    loc_col = next((col for col in cols if 'LOC' in col or 'POS' in col or 'LOCATION' in col),
                   cols[2] if len(cols) > 2 else desc_col)

    # Improved detection of QTY/VEH column
    qty_veh_col = next((col for col in cols if any(term in col for term in ['QTY/VEH', 'QTY_VEH', 'QTY PER VEH', 'QTYVEH', 'QTYPERCAR', 'QTYCAR', 'QTY/CAR'])), None)

    # Look for store location column
    store_loc_col = next((col for col in cols if 'STORE' in col and 'LOC' in col),
                      next((col for col in cols if 'STORELOCATION' in col), None))

    # Find bus model column using the enhanced detection function
    bus_model_col = find_bus_model_column(original_columns)

    if status_callback:
        status_callback(f"Using columns: Part No: {part_no_col}, Description: {desc_col}, Location: {loc_col}, Qty/Bin: {qty_bin_col}")
        if qty_veh_col:
            status_callback(f"Qty/Veh Column: {qty_veh_col}")
        if store_loc_col:
            status_callback(f"Store Location Column: {store_loc_col}")
        if bus_model_col:
            status_callback(f"Bus Model Column: {bus_model_col}")
    else:
        st.write(f"Using columns: Part No: {part_no_col}, Description: {desc_col}, Location: {loc_col}, Qty/Bin: {qty_bin_col}")
        if qty_veh_col:
            st.write(f"Qty/Veh Column: {qty_veh_col}")
        if store_loc_col:
            st.write(f"Store Location Column: {store_loc_col}")
        if bus_model_col:
            st.write(f"Bus Model Column: {bus_model_col}")

    # Create document with minimal margins
    doc = SimpleDocTemplate(output_pdf_path, pagesize=STICKER_PAGESIZE,
                          topMargin=0.2*cm,  # Minimal top margin
                          bottomMargin=(STICKER_HEIGHT - CONTENT_BOX_HEIGHT - 0.2*cm),  # Adjust bottom margin accordingly
                          leftMargin=0.1*cm, rightMargin=0.1*cm)

    content_width = CONTENT_BOX_WIDTH - 0.2*cm
    all_elements = []

    # Process each row as a single sticker
    total_rows = len(df)
    for index, row in df.iterrows():
        # Update progress
        if status_callback:
            status_callback(f"Creating sticker {index+1} of {total_rows} ({int((index+1)/total_rows*100)}%)")
        
        elements = []

        # Extract data
        part_no = str(row[part_no_col])
        desc = str(row[desc_col])
        
        # Extract QTY/BIN properly
        qty_bin = ""
        if qty_bin_col and qty_bin_col in row and pd.notna(row[qty_bin_col]):
            qty_bin = str(row[qty_bin_col])
            
        # Extract QTY/VEH properly
        qty_veh = ""
        if qty_veh_col and qty_veh_col in row and pd.notna(row[qty_veh_col]):
            qty_veh = str(row[qty_veh_col])
        
        location_str = str(row[loc_col]) if loc_col and loc_col in row else ""
        store_location = str(row[store_loc_col]) if store_loc_col and store_loc_col in row else ""
        location_parts = parse_location_string(location_str)

        # Use enhanced bus model detection
        mtm_quantities = detect_bus_model_and_qty(row, qty_veh_col, bus_model_col)

        # Generate QR code with part information
        qr_data = f"Part No: {part_no}\nDescription: {desc}\nLocation: {location_str}\n"
        qr_data += f"Store Location: {store_location}\nQTY/VEH: {qty_veh}\nQTY/BIN: {qty_bin}"
        
        qr_image = generate_qr_code(qr_data)
        if status_callback and qr_image:
            status_callback(f"QR code generated for part: {part_no}")
        
        # Define row heights
        header_row_height = 0.9*cm
        desc_row_height = 1.0*cm
        qty_row_height = 0.5*cm
        location_row_height = 0.5*cm

        # Main table data
        main_table_data = [
            ["Part No", Paragraph(f"{part_no}", bold_style)],
            ["Description", Paragraph(desc[:47] + "..." if len(desc) > 50 else desc, desc_style)],
            ["Qty/Bin", Paragraph(str(qty_bin), qty_style)]
        ]

        # Create main table
        main_table = Table(main_table_data,
                         colWidths=[content_width/3, content_width*2/3],
                         rowHeights=[header_row_height, desc_row_height, qty_row_height])

        main_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1.2, colors.Color(0, 0, 0, alpha=0.95)),  # Darker grid lines
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (0, -1), 11),
        ]))

        elements.append(main_table)

        # Store Location section
        store_loc_label = Paragraph("Store Location", ParagraphStyle(
        name='StoreLoc', fontName='Helvetica-Bold', fontSize=11, alignment=TA_CENTER
        ))
        # Total width for the 7 inner columns (2/3 of full content width)
        inner_table_width = content_width * 2 / 3

        # Define proportional widths - same as Line Location for consistency
        col_proportions = [1.5, 2.5, 0.7, 0.8, 0.8, 0.7, 0.9]
        total_proportion = sum(col_proportions)

        # Calculate column widths based on proportions 
        inner_col_widths = [w * inner_table_width / total_proportion for w in col_proportions]

        # Extract store location values from Excel data
        store_loc_values = extract_store_location_data_from_excel(row)

        store_loc_inner_table = Table(
            [store_loc_values],
            colWidths=inner_col_widths,
            rowHeights=[location_row_height]
        )
        store_loc_inner_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1.2, colors.Color(0, 0, 0, alpha=0.95)),  # Darker grid lines
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),  # Make store location values bold
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        store_loc_table = Table(
            [[store_loc_label, store_loc_inner_table]],
            colWidths=[content_width/3, inner_table_width],
            rowHeights=[location_row_height]
        )
        store_loc_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1.2, colors.Color(0, 0, 0, alpha=0.95)),  # Darker grid lines
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(store_loc_table)

        # Line Location section
        line_loc_label = Paragraph("Line Location", ParagraphStyle(
            name='LineLoc', fontName='Helvetica-Bold', fontSize=11, alignment=TA_CENTER
        ))
        # Extract line location values from Excel data
        location_parts = extract_location_data_from_excel(row)
        location_parts = [
            str(int(float(val))) if isinstance(val, str) and re.match(r'^\d+\.0$', val) else val
            for val in location_parts
        ]
        # Create the inner table
        line_loc_inner_table = Table(
            [location_parts],
            colWidths=inner_col_widths,
            rowHeights=[location_row_height]
        )
        line_loc_inner_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1.2, colors.Color(0, 0, 0, alpha=0.95)),  # Darker grid lines
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),  # Make line location values bold
            ('FONTSIZE', (0, 0), (-1, -1), 9)
        ]))
        # Wrap the label and the inner table in a containing table
        line_loc_table = Table(
            [[line_loc_label, line_loc_inner_table]],
            colWidths=[content_width/3, inner_table_width],
            rowHeights=[location_row_height]
        )
        line_loc_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1.2, colors.Color(0, 0, 0, alpha=0.95)),  # Darker grid lines
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(line_loc_table)

        # Add smaller spacer between line location and bottom section
        elements.append(Spacer(1, 0.5*cm))

        # Bottom section - Enhanced with intelligent bus model detection
        mtm_box_width = 1.2*cm
        mtm_row_height = 1.5*cm

        # Create MTM boxes with detected quantities
        position_matrix_data = [
            ["4W", "3WS", "3WM", "3WC"],
            [
                Paragraph(f"<b>{mtm_quantities['4W']}</b>", ParagraphStyle(
                    name='Bold4W', fontName='Helvetica-Bold', fontSize=10, alignment=TA_CENTER
                )) if mtm_quantities['4W'] else "",
                Paragraph(f"<b>{mtm_quantities['3WS']}</b>", ParagraphStyle(
                    name='Bold3WS', fontName='Helvetica-Bold', fontSize=10, alignment=TA_CENTER
                )) if mtm_quantities['3WS'] else "",
                Paragraph(f"<b>{mtm_quantities['3WM']}</b>", ParagraphStyle(
                    name='Bold3WM', fontName='Helvetica-Bold', fontSize=10, alignment=TA_CENTER
                )) if mtm_quantities['3WM'] else "",
                Paragraph(f"<b>{mtm_quantities['3WC']}</b>", ParagraphStyle(
                    name='Bold3WC', fontName='Helvetica-Bold', fontSize=10, alignment=TA_CENTER
                )) if mtm_quantities['3WC'] else ""
            ]
        ]

        mtm_table = Table(
            position_matrix_data,
            colWidths=[mtm_box_width, mtm_box_width, mtm_box_width, mtm_box_width],
            rowHeights=[mtm_row_height/2, mtm_row_height/2]
        )

        mtm_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 1.2, colors.Color(0, 0, 0, alpha=0.95)),  # Darker grid lines
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))

        # QR code with preserved size
        qr_width = 2.2*cm
        qr_height = 2.2*cm

        if qr_image:
            qr_table = Table(
                [[qr_image]],
                colWidths=[qr_width],
                rowHeights=[qr_height]
            )
        else:
            qr_table = Table(
                [[Paragraph("QR", ParagraphStyle(
                    name='QRPlaceholder', fontName='Helvetica-Bold', fontSize=12, alignment=TA_CENTER
                ))]],
                colWidths=[qr_width],
                rowHeights=[qr_height]
            )

        qr_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        # Adjust spacing for better layout
        left_spacer_width = 0.3*cm
        middle_spacer_width = 0.4*cm  # Reduced from calculated value to 0.3cm
        right_spacer_width = content_width - (mtm_box_width * 4) - qr_width - left_spacer_width - middle_spacer_width

        # Bottom section layout
        bottom_section_data = [
            ["", mtm_table, "", qr_table]
        ]

        bottom_section_table = Table(
            bottom_section_data,
            colWidths=[left_spacer_width, mtm_box_width * 4, right_spacer_width, qr_width],
            rowHeights=[mtm_row_height]
        )

        bottom_section_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))

        elements.append(bottom_section_table)

        # Add all elements to the main list
        all_elements.extend(elements)

        # Add page break if not the last row
        if index < len(df) - 1:
            all_elements.append(PageBreak())

    # Build the PDF
    try:
        doc.build(all_elements, onFirstPage=draw_border, onLaterPages=draw_border)
        if status_callback:
            status_callback(f"PDF created successfully: {output_pdf_path}")
        else:
            st.success(f"PDF created successfully: {output_pdf_path}")
        return output_pdf_path
    except Exception as e:
        error_msg = f"Error creating PDF: {e}"
        if status_callback:
            status_callback(error_msg)
        else:
            st.error(error_msg)
        return None

def main():
    st.set_page_config(page_title="Chakan Bin Label Generator", layout="wide")
    
    st.title("🏷️ Chakan Bin Label Generator")
    st.markdown(
        "<p style='font-size:18px; font-style:italic; margin-top:-10px; text-align:left;'>"
        "Designed and Developed by Agilomatrix</p>",
        unsafe_allow_html=True
    )
    
    # File upload
    uploaded_file = st.file_uploader(
        "Upload Excel or CSV file",
        type=['xlsx', 'xls', 'csv'],
        help="Select a file containing part numbers, descriptions, and location data"
    )
    
    if uploaded_file is not None:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx' if uploaded_file.name.endswith('.xlsx') else '.csv') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_file_path = tmp_file.name
        
        st.success(f"File uploaded: {uploaded_file.name}")
        
        # Preview data
        try:
            if uploaded_file.name.lower().endswith('.csv'):
                df_preview = pd.read_csv(tmp_file_path)
            else:
                df_preview = pd.read_excel(tmp_file_path)
            
            st.subheader("📊 Data Preview")
            st.dataframe(df_preview.head(10))
            
            st.info(f"Total rows: {len(df_preview)}")
            
        except Exception as e:
            st.error(f"Error reading file: {e}")
            return
        
        # Generate stickers button
        if st.button("🏷️ Generate Labels", type="primary"):
            # Create output filename
            output_filename = f"sticker_labels_{uploaded_file.name.split('.')[0]}.pdf"
            
            # Progress container
            progress_container = st.container()
            progress_bar = progress_container.progress(0)
            status_text = progress_container.empty()
            
            def update_status(message):
                status_text.text(message)
                # Update progress bar based on message content
                if "Creating sticker" in message and "of" in message:
                    try:
                        # Extract current/total from message
                        parts = message.split()
                        current = int(parts[2])
                        total = int(parts[4])
                        progress = current / total
                        progress_bar.progress(progress)
                    except:
                        pass
            
            # Generate PDF
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_pdf:
                    pdf_path = generate_sticker_labels(tmp_file_path, tmp_pdf.name, update_status)
                    
                    if pdf_path:
                        # Read the generated PDF
                        with open(pdf_path, 'rb') as pdf_file:
                            pdf_data = pdf_file.read()
                        
                        # Download button
                        st.download_button(
                            label="📥 Download Sticker Labels PDF",
                            data=pdf_data,
                            file_name=output_filename,
                            mime="application/pdf",
                            type="primary"
                        )
                        
                        st.success("✅ Sticker labels generated successfully!")
                        
                        # Clean up temporary files
                        try:
                            os.unlink(tmp_file_path)
                            os.unlink(pdf_path)
                        except:
                            pass
                    
            except Exception as e:
                st.error(f"Error generating stickers: {e}")
                import traceback
                st.code(traceback.format_exc())
    
    else:
        st.info("👆 Please upload an Excel or CSV file to get started")
    
    # Show sample data format
    st.subheader("📋 Reference For Data Format")
    sample_data = {
        'Part No': ['08-DRA-14-02', 'P0012124-07', 'P0012126-07'],
        'Part Desc': ['BELLOW ASSY. WITH RETAINING CLIP', 'GUARD RING (hirkesh)', 'GUARD RING SEAL (hirkesh)'],
        'Bin Type': ['TOTE', 'BIN C', 'BIN A'],
        'Qty/bin': [360, 20, 120],
        'Qty/veh': [10, 5, 2],
        'Bus model': ['3WC', '3WM', '3WS'],
        'Station No': ['CW40RH', 'CW40RH', 'CW40RH'],
        'Rack': ['R', 'R', 'R'],
        'Rack No (1st digit)': [0, 0, 0],
        'Rack No (2nd digit)': [2, 2, 2],
        'Level': ['A', 'A', 'A'],
        'Cell': [1, 2, 3],
        'ABB ZONE': ['HRD', 'HRD', 'HRD'],
        'ABB LOCATION': ['ABF', 'ABF', 'ABF'],
        'ABB FLOOR': [1, 1, 1],
        'ABB RACK NO': [2, 2, 2],
        'ABB LEVEL IN RACK': ['C', 'D', 'B'],
        'ABB CELL': [0, 0, 0],
        'ABB NO': [1, 4, 5],
    }
    
    sample_df = pd.DataFrame(sample_data)
    st.dataframe(sample_df)
    
    st.markdown("""
    **Column Requirements:**
    - **Part No**: Part number or identifier
    - **Part Desc**: Part description
    - **Bin Type**: Type of bin (TOTE, BIN A, BIN B, BIN C, etc.)
    - **Qty/bin**: Quantity per bin
    - **Qty/veh**: Quantity per vehicle
    - **Bus model**: Bus model type (3WC, 3WM, 3WS, 4W, etc.)
    - **Station No**: Station identifier
    - **Rack**: Rack identifier
    - **Rack No (1st digit)**: First digit of rack number
    - **Rack No (2nd digit)**: Second digit of rack number
    - **Level**: Storage level (A, B, C, etc.)
    - **Cell**: Cell number
    - **ABB ZONE**: ABB zone identifier
    - **ABB LOCATION**: ABB location code
    - **ABB FLOOR**: ABB floor number
    - **ABB RACK NO**: ABB rack number
    - **ABB LEVEL IN RACK**: ABB level in rack
    - **ABB CELL**: ABB cell number
    - **ABB NO**: ABB number
    
    ℹ️ Column names are case-insensitive and can contain variations (e.g., 'Part No', 'PART_NO', 'part_no', etc.)
    
    📍 **Location Information**: The system will automatically combine location fields to create a comprehensive storage location identifier.
    """)

if __name__ == "__main__":
    main()
