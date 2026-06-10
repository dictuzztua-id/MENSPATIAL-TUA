import streamlit as st
import pandas as pd
import numpy as np
from fuzzywuzzy import fuzz, process
import requests
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster, HeatMap
import re
import io
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

# Page configuration
st.set_page_config(
    page_title="Outlet Detail Checker",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for elegant UI
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #2c3e50;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
    }
    .info-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 0.5rem;
        color: white;
        text-align: center;
    }
    .stDataFrame {
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_data():
    """Load all data files"""
    try:
        df_outlet = pd.read_excel('MASTER OUTLET AQUA.xlsx')
        df_rute = pd.read_excel('RUTE ALL.xlsx')
        df_quadran = pd.read_excel('Quadran.xlsx')
        
        # Standardize column names
        df_outlet.columns = df_outlet.columns.str.strip()
        df_rute.columns = df_rute.columns.str.strip()
        df_quadran.columns = df_quadran.columns.str.strip()
        
        # Preprocess for analytics
        df_outlet_clean = df_outlet.copy()
        df_outlet_clean['Latitude'] = pd.to_numeric(df_outlet_clean['Latitude'], errors='coerce')
        df_outlet_clean['Longitude'] = pd.to_numeric(df_outlet_clean['Longitude'], errors='coerce')
        if 'KREDIT_LIMIT' in df_outlet_clean.columns:
            df_outlet_clean['KREDIT_LIMIT'] = pd.to_numeric(df_outlet_clean['KREDIT_LIMIT'], errors='coerce').fillna(0)
        
        return df_outlet, df_rute, df_quadran, df_outlet_clean
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None, None, None, None

def clean_coordinates(lat, lon):
    """Clean and validate coordinates"""
    try:
        if pd.isna(lat) or pd.isna(lon):
            return None, None
        lat = float(lat)
        lon = float(lon)
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
        return None, None
    except:
        return None, None

def search_outlet(query, df_outlet, search_type='exact'):
    """Search for outlet by ID or name with different search types"""
    if not query:
        return pd.DataFrame()
    
    query = str(query).strip().upper()
    
    if search_type == 'exact':
        # Exact match on ID or Name
        mask = (df_outlet['ID_PELANGGAN'].astype(str).str.upper() == query) | \
               (df_outlet['NAMA_PELANGGAN'].astype(str).str.upper() == query)
        return df_outlet[mask]
    
    elif search_type == 'contains':
        # Partial match
        mask = (df_outlet['ID_PELANGGAN'].astype(str).str.upper().str.contains(query, na=False)) | \
               (df_outlet['NAMA_PELANGGAN'].astype(str).str.upper().str.contains(query, na=False))
        return df_outlet[mask]
    
    elif search_type == 'fuzzy':
        # Fuzzy matching using fuzzywuzzy
        outlet_names = df_outlet['NAMA_PELANGGAN'].astype(str).tolist()
        outlet_ids = df_outlet['ID_PELANGGAN'].astype(str).tolist()
        
        # Search in names
        name_matches = process.extract(query, outlet_names, limit=10, scorer=fuzz.partial_ratio)
        # Search in IDs
        id_matches = process.extract(query, outlet_ids, limit=10, scorer=fuzz.partial_ratio)
        
        # Get indices of matches with score >= 70
        matched_indices = set()
        for match, score in name_matches + id_matches:
            if score >= 70:
                indices = df_outlet[
                    (df_outlet['NAMA_PELANGGAN'].astype(str) == match) | 
                    (df_outlet['ID_PELANGGAN'].astype(str) == match)
                ].index.tolist()
                matched_indices.update(indices)
        
        if matched_indices:
            return df_outlet.loc[list(matched_indices)]
        return pd.DataFrame()
    
    return pd.DataFrame()

def get_route_info(outlet_id, df_rute):
    """Get route information for an outlet"""
    routes = df_rute[df_rute['ID PELANGGAN'] == outlet_id]
    return routes

def determine_quadran(lat, lon, kelurahan, kecamatan, kab_kot, province, df_quadran):
    """Determine quadran based on location"""
    if pd.isna(kelurahan) or pd.isna(kecamatan) or pd.isna(kab_kot) or pd.isna(province):
        return "Tidak Diketahui"
    
    # Try exact match first
    mask = (df_quadran['KELURAHAN'].astype(str).str.upper() == str(kelurahan).upper()) & \
           (df_quadran['KECAMATAN'].astype(str).str.upper() == str(kecamatan).upper()) & \
           (df_quadran['KAB_KOT'].astype(str).str.upper() == str(kab_kot).upper()) & \
           (df_quadran['PROVINCE'].astype(str).str.upper() == str(province).upper())
    
    matches = df_quadran[mask]
    
    if len(matches) > 0:
        return matches.iloc[0]['QUADRAN']
    
    # Try partial match on kelurahan and kecamatan
    mask_partial = (df_quadran['KELURAHAN'].astype(str).str.upper().str.contains(str(kelurahan).upper(), na=False)) & \
                   (df_quadran['KECAMATAN'].astype(str).str.upper().str.contains(str(kecamatan).upper(), na=False))
    
    matches_partial = df_quadran[mask_partial]
    
    if len(matches_partial) > 0:
        return matches_partial.iloc[0]['QUADRAN']
    
    return "Tidak Diketahui"

def reverse_geocode(lat, lon):
    """Reverse geocode coordinates to get address components"""
    try:
        response = requests.get(
            f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}",
            headers={'User-Agent': 'StreamlitApp/1.0'},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            address = data.get('address', {})
            return {
                'kelurahan': address.get('neighbourhood', address.get('suburb', '')),
                'kecamatan': address.get('city_district', address.get('town', '')),
                'kab_kot': address.get('city', address.get('county', '')),
                'province': address.get('state', '')
            }
    except:
        pass
    return None

def calculate_distance(user_lat, user_lon, outlet_lat, outlet_lon):
    """Calculate distance between two points in kilometers"""
    try:
        coord1 = (user_lat, user_lon)
        coord2 = (outlet_lat, outlet_lon)
        distance = geodesic(coord1, coord2).kilometers
        return round(distance, 2)
    except:
        return None

def create_map(outlet_lat, outlet_lon, user_lat=None, user_lon=None, outlet_name="", df_outlet_clean=None, show_all_outlets=False):
    """Create interactive map with outlet and user location"""
    m = folium.Map(location=[outlet_lat, outlet_lon], zoom_start=13)
    
    # Add outlet marker
    folium.Marker(
        [outlet_lat, outlet_lon],
        popup=f"<b>{outlet_name}</b>",
        icon=folium.Icon(color='blue', icon='store', prefix='fa')
    ).add_to(m)
    
    # Add user location marker if provided
    if user_lat and user_lon:
        folium.Marker(
            [user_lat, user_lon],
            popup="<b>Lokasi Anda</b>",
            icon=folium.Icon(color='red', icon='user', prefix='fa')
        ).add_to(m)
        
        # Draw line between user and outlet
        folium.PolyLine(
            locations=[[user_lat, user_lon], [outlet_lat, outlet_lon]],
            color='green',
            weight=3,
            opacity=0.7
        ).add_to(m)
    
    # Show all outlets as cluster if requested
    if show_all_outlets and df_outlet_clean is not None:
        outlets_with_coords = df_outlet_clean[
            df_outlet_clean['Latitude'].notna() & 
            df_outlet_clean['Longitude'].notna()
        ]
        
        if len(outlets_with_coords) > 0:
            marker_cluster = MarkerCluster().add_to(m)
            
            for idx, row in outlets_with_coords.iterrows():
                folium.Marker(
                    [row['Latitude'], row['Longitude']],
                    popup=f"{row.get('ID_PELANGGAN', '')} - {row.get('NAMA_PELANGGAN', '')}",
                    icon=folium.Icon(color='lightblue', icon='store', prefix='fa')
                ).add_to(marker_cluster)
    
    return m

def create_heatmap(df_outlet_clean):
    """Create heatmap of outlet density"""
    outlets_with_coords = df_outlet_clean[
        df_outlet_clean['Latitude'].notna() & 
        df_outlet_clean['Longitude'].notna()
    ]
    
    if len(outlets_with_coords) == 0:
        return None
    
    heat_data = outlets_with_coords[['Latitude', 'Longitude']].values.tolist()
    
    m = folium.Map(
        location=[outlets_with_coords['Latitude'].mean(), outlets_with_coords['Longitude'].mean()],
        zoom_start=10
    )
    
    HeatMap(heat_data, radius=15, blur=20, max_zoom=1).add_to(m)
    
    return m

def export_to_excel(df, filename_prefix="outlet_data"):
    """Export dataframe to Excel for download"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Data')
    output.seek(0)
    return output.getvalue()

def main():
    # Header
    st.markdown('<h1 class="main-header">🏪 Outlet Detail Checker</h1>', unsafe_allow_html=True)
    st.markdown("Cari detail outlet, rute, dan kuadran dengan mudah")
    
    # Load data
    df_outlet, df_rute, df_quadran, df_outlet_clean = load_data()
    
    if df_outlet is None:
        st.error("Gagal memuat data. Pastikan file Excel tersedia.")
        return
    
    # Navigation menu
    st.sidebar.markdown("---")
    st.sidebar.subheader("📱 Menu Utama")
    
    menu_options = [
        "🔍 Cari Outlet",
        "📊 Dashboard Analytics",
        "🗺️ Peta Sebaran Outlet",
        "💾 Export Data"
    ]
    
    selected_menu = st.sidebar.selectbox("Pilih Menu:", menu_options)
    
    # Sidebar for search (only show in search mode)
    if selected_menu == "🔍 Cari Outlet":
        st.sidebar.markdown("---")
        st.sidebar.header("🔍 Pencarian Outlet")
        
        search_query = st.sidebar.text_input(
            "Masukkan ID Outlet atau Nama Outlet",
            placeholder="Contoh: 343-0000001 atau REJEKI 2"
        )
        
        search_type = st.sidebar.selectbox(
            "Tipe Pencarian",
            ["exact", "contains", "fuzzy"],
            format_func=lambda x: {
                "exact": "Exact Match (Persis)",
                "contains": "Contains (Mengandung)",
                "fuzzy": "Fuzzy Match (Mirip)"
            }[x]
        )
        
        search_button = st.sidebar.button("🔎 Cari Outlet", type="primary", use_container_width=True)
        
        st.sidebar.divider()
        
        # User location input
        st.sidebar.header("📍 Lokasi Anda")
        st.sidebar.info("Opsional: Masukkan koordinat untuk menghitung jarak")
        
        user_lat = st.sidebar.number_input(
            "Latitude Anda",
            min_value=-90.0,
            max_value=90.0,
            value=None,
            format="%.6f",
            key="user_lat"
        )
        
        user_lon = st.sidebar.number_input(
            "Longitude Anda",
            min_value=-180.0,
            max_value=180.0,
            value=None,
            format="%.6f",
            key="user_lon"
        )
        
        # Geolocate button
        if st.sidebar.button("🌐 Gunakan Lokasi Saya", use_container_width=True):
            st.sidebar.write("Untuk menggunakan lokasi otomatis, silakan masukkan koordinat manual atau gunakan browser yang mendukung geolocation.")
        
        # Main content area for search results
        if search_query and search_button:
            results = search_outlet(search_query, df_outlet, search_type)
            
            if len(results) == 0:
                st.warning("❌ Outlet tidak ditemukan. Coba tipe pencarian lain atau periksa kembali input Anda.")
            else:
                st.success(f"✅ Ditemukan {len(results)} outlet")
                
                # If multiple results, show selection
                if len(results) > 1:
                    st.subheader("Pilih Outlet:")
                    outlet_options = results.apply(
                        lambda x: f"{x['ID_PELANGGAN']} - {x['NAMA_PELANGGAN']}", axis=1
                    ).tolist()
                    
                    selected = st.selectbox("Pilih outlet yang diinginkan:", outlet_options)
                    selected_idx = outlet_options.index(selected)
                    outlet = results.iloc[selected_idx]
                else:
                    outlet = results.iloc[0]
                
                st.divider()
                
                # Display outlet details
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.markdown('<h3 class="sub-header">📋 Detail Outlet</h3>', unsafe_allow_html=True)
                    
                    # Basic info cards
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("ID Pelanggan", outlet['ID_PELANGGAN'])
                    with c2:
                        st.metric("Status", outlet['STATUS_PELANGGAN'])
                    with c3:
                        st.metric("Segmen", outlet['SEGMEN'])
                    
                    st.markdown('<div class="info-box">', unsafe_allow_html=True)
                    st.write(f"**Nama Outlet:** {outlet['NAMA_PELANGGAN']}")
                    st.write(f"**Alamat:** {outlet['ALAMAT']}")
                    st.write(f"**Kelurahan:** {outlet['KELURAHAN']}")
                    st.write(f"**Kecamatan:** {outlet['KECAMATAN']}")
                    st.write(f"**Kota/Kabupaten:** {outlet['KOTA']}")
                    st.write(f"**Provinsi:** {outlet['PROVINSI']}")
                    st.write(f"**Kode Pos:** {outlet['KODE_POS']}")
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                    # Contact info
                    st.markdown('<h4 class="sub-header">📞 Kontak</h4>', unsafe_allow_html=True)
                    contact_cols = st.columns(3)
                    with contact_cols[0]:
                        if pd.notna(outlet['TELP_1']):
                            st.info(f"Telp 1: {outlet['TELP_1']}")
                    with contact_cols[1]:
                        if pd.notna(outlet['TELP_2']):
                            st.info(f"Telp 2: {outlet['TELP_2']}")
                    with contact_cols[2]:
                        if pd.notna(outlet['TELP_3']):
                            st.info(f"Telp 3: {outlet['TELP_3']}")
                    
                    if pd.notna(outlet['KONTAK_PERSON']):
                        st.write(f"**Kontak Person:** {outlet['KONTAK_PERSON']}")
                    
                    # Additional info
                    st.markdown('<h4 class="sub-header">💼 Informasi Bisnis</h4>', unsafe_allow_html=True)
                    biz_cols = st.columns(4)
                    with biz_cols[0]:
                        st.write(f"**Tempo:** {outlet['TEMPO_PEMBAYARAN']}")
                    with biz_cols[1]:
                        st.write(f"**Tipe:** {outlet['TIPE_PELANGGAN']}")
                    with biz_cols[2]:
                        st.write(f"**Limit:** Rp {outlet['KREDIT_LIMIT']:,.0f}")
                    with biz_cols[3]:
                        st.write(f"**Depo:** {outlet['DEPO_JUAL']}")
                    
                    # Dates
                    date_cols = st.columns(2)
                    with date_cols[0]:
                        st.write(f"**Tanggal Join:** {outlet['TANGGAL_JOIN']}")
                    with date_cols[1]:
                        if pd.notna(outlet['TANGGAL_STOP']) and str(outlet['TANGGAL_STOP']) != '00:00:00':
                            st.write(f"**Tanggal Stop:** {outlet['TANGGAL_STOP']}")
                
                with col2:
                    st.markdown('<h3 class="sub-header">🗺️ Peta Lokasi</h3>', unsafe_allow_html=True)
                    
                    lat, lon = clean_coordinates(outlet['Latitude'], outlet['Longitude'])
                    
                    if lat and lon:
                        # Create map
                        user_lat_clean = user_lat if user_lat else None
                        user_lon_clean = user_lon if user_lon else None
                        
                        m = create_map(lat, lon, user_lat_clean, user_lon_clean, outlet['NAMA_PELANGGAN'])
                        st_folium(m, width=400, height=400)
                        
                        # Calculate distance
                        if user_lat_clean and user_lon_clean:
                            distance = calculate_distance(user_lat_clean, user_lon_clean, lat, lon)
                            if distance:
                                st.markdown(f'<div class="metric-card"><h3>📏 Jarak: {distance} km</h3></div>', unsafe_allow_html=True)
                        
                        # Coordinates display
                        st.code(f"Latitude: {lat}\nLongitude: {lon}")
                    else:
                        st.warning("⚠️ Koordinat tidak tersedia untuk outlet ini")
                
                st.divider()
                
                # Route Information
                st.markdown('<h3 class="sub-header">🚚 Informasi Rute</h3>', unsafe_allow_html=True)
                route_info = get_route_info(outlet['ID_PELANGGAN'], df_rute)
                
                if len(route_info) > 0:
                    route = route_info.iloc[0]
                    
                    route_col1, route_col2 = st.columns(2)
                    
                    with route_col1:
                        st.markdown('<div class="info-box">', unsafe_allow_html=True)
                        st.write(f"**ID Rute:** {route['ID RUTE']}")
                        st.write(f"**Nama Rute:** {route['NAMA RUTE']}")
                        st.write(f"**Tipe Rute:** {route['TIPE RUTE']}")
                        st.write(f"**Sales:** {route['NAMA SALES']} ({route['ID SALES']})")
                        st.write(f"**Supervisor:** {route['NAMA SUPERVISOR']}")
                        st.write(f"**Depo:** {route['NAMA DEPO']}")
                        st.markdown('</div>', unsafe_allow_html=True)
                    
                    with route_col2:
                        # Visit schedule
                        st.write("**Jadwal Kunjungan:**")
                        days = ['SENIN', 'SELASA', 'RABU', 'KAMIS', 'JUMAT', 'SABTU', 'MINGGU']
                        visit_days = []
                        for day in days:
                            if pd.notna(route.get(day)) and route.get(day) == 'V':
                                visit_days.append(day)
                        
                        if visit_days:
                            for day in visit_days:
                                st.success(f"✓ {day}")
                        else:
                            # Check MINGGU_1 to MINGGU_4
                            minggu_cols = st.columns(4)
                            for i, col in enumerate(minggu_cols, 1):
                                week_col = f'MINGGU_{i}'
                                if pd.notna(route.get(week_col)) and route.get(week_col) == 'V':
                                    with col:
                                        st.success(f"Minggu {i}")
                    
                    # Additional route info
                    st.markdown('<div class="info-box">', unsafe_allow_html=True)
                    st.write(f"**Divisi:** {route['DIVISI']}")
                    st.write(f"**Department:** {route['DEPARTMENT']}")
                    st.write(f"**Tanggal Jadi Pelanggan:** {route['TANGGAL JADI PELANGGAN']}")
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.info("ℹ️ Tidak ada informasi rute untuk outlet ini")
                
                st.divider()
                
                # Quadran Determination
                st.markdown('<h3 class="sub-header">📍 Penentuan Kuadran</h3>', unsafe_allow_html=True)
                
                quadran_col1, quadran_col2 = st.columns(2)
                
                with quadran_col1:
                    # Get location data
                    kelurahan = outlet['KELURAHAN']
                    kecamatan = outlet['KECAMATAN']
                    kab_kot = outlet['KOTA']
                    province = outlet['PROVINSI']
                    
                    # Try reverse geocoding if coordinates available
                    if lat and lon:
                        if st.button("🔄 Update dari Koordinat (Reverse Geocode)", key="reverse_geo"):
                            with st.spinner("Sedang melakukan reverse geocoding..."):
                                geo_result = reverse_geocode(lat, lon)
                                if geo_result:
                                    st.success("Reverse geocoding berhasil!")
                                    if geo_result['kelurahan']:
                                        kelurahan = geo_result['kelurahan']
                                    if geo_result['kecamatan']:
                                        kecamatan = geo_result['kecamatan']
                                    if geo_result['kab_kot']:
                                        kab_kot = geo_result['kab_kot']
                                    if geo_result['province']:
                                        province = geo_result['province']
                                else:
                                    st.warning("Gagal melakukan reverse geocoding")
                    
                    st.write("**Data Lokasi untuk Lookup:**")
                    st.write(f"- Provinsi: {province}")
                    st.write(f"- Kota/Kab: {kab_kot}")
                    st.write(f"- Kecamatan: {kecamatan}")
                    st.write(f"- Kelurahan: {kelurahan}")
                
                with quadran_col2:
                    # Determine quadran
                    quadran = determine_quadran(lat, lon, kelurahan, kecamatan, kab_kot, province, df_quadran)
                    
                    if quadran != "Tidak Diketahui":
                        st.markdown(f'<div class="metric-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);"><h2>🎯 Kuadran: {quadran}</h2></div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="metric-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);"><h2>❓ Kuadran: Tidak Diketahui</h2></div>', unsafe_allow_html=True)
                        st.info("Kuadran tidak dapat ditentukan. Pastikan data kelurahan/kecamatan sesuai dengan database quadran.")
                
                # Show quadran lookup table sample
                with st.expander("📊 Lihat Aturan Pembagian Kuadran"):
                    st.write("Berikut adalah contoh aturan pembagian kuadran:")
                    st.dataframe(df_quadran.head(20), use_container_width=True)
                    st.write(f"Total aturan: {len(df_quadran)} baris")
        else:
            # Welcome message when no search performed
            st.markdown("""
            <div style="text-align: center; padding: 3rem;">
                <h2>Selamat Datang di Fitur Pencarian Outlet</h2>
                <p>Masukkan ID atau nama outlet di sidebar untuk memulai pencarian</p>
            </div>
            """, unsafe_allow_html=True)
    
    # Dashboard Analytics Menu
    elif selected_menu == "📊 Dashboard Analytics":
        st.header("📊 Dashboard Analytics")
        st.markdown("Analisis data outlet secara keseluruhan")
        
        # Overview statistics
        st.subheader("📈 Statistik Umum")
        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        with stat_col1:
            st.metric("Total Outlet", f"{len(df_outlet):,}")
        with stat_col2:
            outlets_with_coords = df_outlet[df_outlet['Latitude'].notna() & df_outlet['Longitude'].notna()]
            st.metric("Outlet dengan Koordinat", f"{len(outlets_with_coords):,}")
        with stat_col3:
            st.metric("Total Rute", f"{len(df_rute):,}")
        with stat_col4:
            st.metric("Aturan Kuadran", f"{len(df_quadran):,}")
        
        st.divider()
        
        # Distribution by status
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Distribusi Status Pelanggan")
            if 'STATUS_PELANGGAN' in df_outlet.columns:
                status_counts = df_outlet['STATUS_PELANGGAN'].value_counts().reset_index()
                status_counts.columns = ['Status', 'Jumlah']
                fig_status = px.pie(status_counts, values='Jumlah', names='Status', 
                                   title='Proporsi Status Pelanggan',
                                   color_discrete_sequence=px.colors.qualitative.Set3)
                st.plotly_chart(fig_status, use_container_width=True)
        
        with col2:
            st.subheader("Distribusi Segmen")
            if 'SEGMEN' in df_outlet.columns:
                segmen_counts = df_outlet['SEGMEN'].value_counts().reset_index()
                segmen_counts.columns = ['Segmen', 'Jumlah']
                fig_segmen = px.bar(segmen_counts, x='Segmen', y='Jumlah',
                                   title='Jumlah Outlet per Segmen',
                                   color='Jumlah',
                                   color_continuous_scale='Blues')
                st.plotly_chart(fig_segmen, use_container_width=True)
        
        st.divider()
        
        # Geographic distribution
        st.subheader("🗺️ Distribusi Geografis")
        if 'PROVINSI' in df_outlet.columns:
            prov_counts = df_outlet['PROVINSI'].value_counts().head(10).reset_index()
            prov_counts.columns = ['Provinsi', 'Jumlah']
            fig_prov = px.bar(prov_counts, x='Jumlah', y='Provinsi', orientation='h',
                             title='Top 10 Provinsi dengan Terbanyak Outlet',
                             color='Jumlah',
                             color_continuous_scale='Viridis')
            st.plotly_chart(fig_prov, use_container_width=True)
        
        # Credit limit analysis
        if 'KREDIT_LIMIT' in df_outlet_clean.columns:
            st.divider()
            st.subheader("💰 Analisis Kredit Limit")
            
            credit_stats = df_outlet_clean['KREDIT_LIMIT'].describe()
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Rata-rata", f"Rp {credit_stats['mean']:,.0f}")
            with c2:
                st.metric("Median", f"Rp {credit_stats['50%']:,.0f}")
            with c3:
                st.metric("Max", f"Rp {credit_stats['max']:,.0f}")
            with c4:
                st.metric("Min", f"Rp {credit_stats['min']:,.0f}")
            
            fig_credit = px.histogram(df_outlet_clean, x='KREDIT_LIMIT', nbins=50,
                                     title='Distribusi Kredit Limit',
                                     labels={'KREDIT_LIMIT': 'Kredit Limit (Rp)'},
                                     opacity=0.7)
            st.plotly_chart(fig_credit, use_container_width=True)
    
    # Map Menu
    elif selected_menu == "🗺️ Peta Sebaran Outlet":
        st.header("🗺️ Peta Sebaran Outlet")
        st.markdown("Visualisasi sebaran outlet di peta")
        
        map_type = st.selectbox("Pilih Tipe Peta:", ["Marker Cluster", "Heatmap"])
        
        if map_type == "Marker Cluster":
            st.info(f"Menampilkan {len(df_outlet_clean[df_outlet_clean['Latitude'].notna()])} outlet dengan koordinat valid")
            
            # Create map centered on Indonesia
            m = folium.Map(location=[-2.5, 118], zoom_start=5)
            
            outlets_with_coords = df_outlet_clean[
                df_outlet_clean['Latitude'].notna() & 
                df_outlet_clean['Longitude'].notna()
            ]
            
            if len(outlets_with_coords) > 0:
                marker_cluster = MarkerCluster().add_to(m)
                
                for idx, row in outlets_with_coords.iterrows():
                    popup_html = f"""
                    <b>{row.get('NAMA_PELANGGAN', 'N/A')}</b><br>
                    ID: {row.get('ID_PELANGGAN', 'N/A')}<br>
                    Alamat: {row.get('ALAMAT', 'N/A')}
                    """
                    folium.Marker(
                        [row['Latitude'], row['Longitude']],
                        popup=popup_html,
                        icon=folium.Icon(color='blue', icon='store', prefix='fa')
                    ).add_to(marker_cluster)
                
                st_folium(m, width=1200, height=600)
        
        elif map_type == "Heatmap":
            st.info("Heatmap menunjukkan kepadatan outlet")
            
            heat_map = create_heatmap(df_outlet_clean)
            if heat_map:
                st_folium(heat_map, width=1200, height=600)
            else:
                st.warning("Tidak ada data koordinat yang valid untuk membuat heatmap")
    
    # Export Menu
    elif selected_menu == "💾 Export Data":
        st.header("💾 Export Data")
        st.markdown("Download data outlet dalam format Excel")
        
        export_option = st.selectbox(
            "Pilih data yang ingin diexport:",
            ["Semua Outlet", "Outlet dengan Koordinat", "Outlet Aktif", "Data Rute", "Aturan Kuadran"]
        )
        
        if export_option == "Semua Outlet":
            df_to_export = df_outlet
            filename = "MASTER_OUTLET_AQUA.xlsx"
        elif export_option == "Outlet dengan Koordinat":
            df_to_export = df_outlet_clean[
                df_outlet_clean['Latitude'].notna() & 
                df_outlet_clean['Longitude'].notna()
            ]
            filename = "OUTLET_DENGAN_KOORDINAT.xlsx"
        elif export_option == "Outlet Aktif":
            if 'STATUS_PELANGGAN' in df_outlet.columns:
                df_to_export = df_outlet[df_outlet['STATUS_PELANGGAN'] == 'AKTIF']
                filename = "OUTLET_AKTIF.xlsx"
            else:
                df_to_export = df_outlet
                filename = "MASTER_OUTLET_AQUA.xlsx"
        elif export_option == "Data Rute":
            df_to_export = df_rute
            filename = "DATA_RUTE.xlsx"
        else:  # Aturan Kuadran
            df_to_export = df_quadran
            filename = "ATURAN_KUADRAN.xlsx"
        
        st.write(f"**Preview Data:**")
        st.dataframe(df_to_export.head(10), use_container_width=True)
        st.write(f"Total baris: {len(df_to_export):,}")
        
        # Create download button
        excel_data = export_to_excel(df_to_export)
        
        st.download_button(
            label=f"📥 Download {filename}",
            data=excel_data,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

if __name__ == "__main__":
    main()
