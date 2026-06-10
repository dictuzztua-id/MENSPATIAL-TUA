import streamlit as st
import pandas as pd
import numpy as np
from fuzzywuzzy import fuzz, process
from geopy.distance import geodesic
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
import io
from datetime import datetime
import plotly.express as px

# Page configuration
st.set_page_config(
    page_title="Outlet Detail Checker",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="collapsed"
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
    div[data-testid="stMetricValue"] {
        font-size: 24px;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'outlet_loaded' not in st.session_state:
    st.session_state.outlet_loaded = False
if 'rute_loaded' not in st.session_state:
    st.session_state.rute_loaded = False
if 'quadran_loaded' not in st.session_state:
    st.session_state.quadran_loaded = False
if 'outlet_index' not in st.session_state:
    st.session_state.outlet_index = None

@st.cache_data(ttl=3600)
def load_outlet_data():
    """Load outlet data with minimal columns needed"""
    try:
        with st.spinner('Memuat data outlet...'):
            df = pd.read_excel('MASTER OUTLET AQUA.xlsx')
            
            # Standardize column names
            df.columns = df.columns.str.strip()
            
            # Keep only essential columns to reduce memory
            essential_cols = ['ID_PELANGGAN', 'NAMA_PELANGGAN', 'ALAMAT', 'KONTAK', 
                            'TELEPON', 'STATUS_PELANGGAN', 'SEGMENTASI', 
                            'KREDIT_LIMIT', 'Latitude', 'Longitude',
                            'KELURAHAN', 'KECAMATAN', 'KAB_KOT', 'PROVINSI']
            
            available_cols = [c for c in essential_cols if c in df.columns]
            df = df[available_cols].copy()
            
            # Clean coordinates once
            df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
            df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')
            
            # Clean kredit limit
            if 'KREDIT_LIMIT' in df.columns:
                df['KREDIT_LIMIT'] = pd.to_numeric(df['KREDIT_LIMIT'], errors='coerce').fillna(0)
            
            # Create search index
            df['SEARCH_KEY'] = (df['ID_PELANGGAN'].astype(str) + ' ' + 
                               df['NAMA_PELANGGAN'].astype(str)).str.upper()
            
            st.session_state.outlet_loaded = True
            return df
    except Exception as e:
        st.error(f"Error loading outlet data: {e}")
        return None

@st.cache_data(ttl=3600)
def load_rute_data():
    """Load route data"""
    try:
        with st.spinner('Memuat data rute...'):
            df = pd.read_excel('RUTE ALL.xlsx')
            df.columns = df.columns.str.strip()
            st.session_state.rute_loaded = True
            return df
    except Exception as e:
        st.error(f"Error loading route data: {e}")
        return None

@st.cache_data(ttl=3600)
def load_quadran_data():
    """Load quadran data"""
    try:
        with st.spinner('Memuat data quadran...'):
            df = pd.read_excel('Quadran.xlsx')
            df.columns = df.columns.str.strip()
            
            # Create lookup key
            if 'KELURAHAN' in df.columns and 'KECAMATAN' in df.columns:
                df['LOOKUP_KEY'] = (df['KELURAHAN'].astype(str).str.upper() + '|' + 
                                   df['KECAMATAN'].astype(str).str.upper())
            
            st.session_state.quadran_loaded = True
            return df
    except Exception as e:
        st.error(f"Error loading quadran data: {e}")
        return None

def get_outlet_data():
    """Get outlet data, load if needed"""
    if not st.session_state.outlet_loaded:
        return load_outlet_data()
    return load_outlet_data()

def get_rute_data():
    """Get route data, load if needed"""
    if not st.session_state.rute_loaded:
        return load_rute_data()
    return load_rute_data()

def get_quadran_data():
    """Get quadran data, load if needed"""
    if not st.session_state.quadran_loaded:
        return load_quadran_data()
    return load_quadran_data()

def search_outlet(query, df_outlet, search_type='contains'):
    """Search for outlet by ID or name"""
    if not query or df_outlet is None:
        return pd.DataFrame()
    
    query = str(query).strip().upper()
    
    if search_type == 'exact':
        mask = df_outlet['SEARCH_KEY'] == query
        return df_outlet[mask]
    
    elif search_type == 'contains':
        mask = df_outlet['SEARCH_KEY'].str.contains(query, na=False)
        return df_outlet[mask]
    
    elif search_type == 'fuzzy':
        # Limit to first 5000 rows for performance
        sample_df = df_outlet.head(5000)
        search_keys = sample_df['SEARCH_KEY'].tolist()
        
        matches = process.extract(query, search_keys, limit=20, scorer=fuzz.partial_ratio)
        
        matched_indices = []
        for match, score in matches:
            if score >= 70:
                idx = sample_df[sample_df['SEARCH_KEY'] == match].index
                matched_indices.extend(idx.tolist())
        
        if matched_indices:
            return df_outlet.loc[matched_indices].drop_duplicates()
        return pd.DataFrame()
    
    return pd.DataFrame()

def get_route_info(outlet_id, df_rute):
    """Get route information for an outlet"""
    if df_rute is None or outlet_id is None:
        return pd.DataFrame()
    
    # Try different column names
    id_col = None
    for col in ['ID PELANGGAN', 'ID_PELANGGAN', 'CUSTOMER_ID']:
        if col in df_rute.columns:
            id_col = col
            break
    
    if id_col:
        routes = df_rute[df_rute[id_col] == outlet_id]
        return routes
    return pd.DataFrame()

def determine_quadran(kelurahan, kecamatan, df_quadran):
    """Determine quadran based on location"""
    if df_quadran is None or pd.isna(kelurahan) or pd.isna(kecamatan):
        return "Tidak Diketahui"
    
    kelurahan = str(kelurahan).strip().upper()
    kecamatan = str(kecamatan).strip().upper()
    
    # Try exact match
    lookup_key = f"{kelurahan}|{kecamatan}"
    if 'LOOKUP_KEY' in df_quadran.columns:
        mask = df_quadran['LOOKUP_KEY'] == lookup_key
        matches = df_quadran[mask]
        if len(matches) > 0:
            return matches.iloc[0]['QUADRAN']
    
    # Try partial match
    mask = (df_quadran['KELURAHAN'].astype(str).str.upper().str.contains(kelurahan, na=False)) & \
           (df_quadran['KECAMATAN'].astype(str).str.upper().str.contains(kecamatan, na=False))
    
    matches = df_quadran[mask]
    if len(matches) > 0:
        return matches.iloc[0]['QUADRAN']
    
    return "Tidak Diketahui"

def calculate_distance(user_lat, user_lon, outlet_lat, outlet_lon):
    """Calculate distance between two points in kilometers"""
    try:
        coord1 = (user_lat, user_lon)
        coord2 = (outlet_lat, outlet_lon)
        return round(geodesic(coord1, coord2).kilometers, 2)
    except:
        return None

def create_map(outlets, center_lat=-2.5, center_lon=118.0, zoom=5):
    """Create folium map with markers"""
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom)
    
    marker_cluster = MarkerCluster().add_to(m)
    
    count = 0
    for _, row in outlets.iterrows():
        if pd.notna(row.get('Latitude')) and pd.notna(row.get('Longitude')):
            lat = row['Latitude']
            lon = row['Longitude']
            
            popup_html = f"""
            <div style="width: 200px;">
                <b>{row.get('NAMA_PELANGGAN', 'N/A')}</b><br>
                ID: {row.get('ID_PELANGGAN', 'N/A')}<br>
                {row.get('ALAMAT', 'N/A')[:50]}...
            </div>
            """
            
            folium.Marker(
                location=[lat, lon],
                popup=folium.Popup(popup_html, max_width=250),
                tooltip=row.get('NAMA_PELANGGAN', 'Outlet'),
                icon=folium.Icon(color='blue', icon='store', prefix='fa')
            ).add_to(marker_cluster)
            count += 1
            
            # Limit markers for performance
            if count >= 100:
                break
    
    return m

def main():
    st.markdown('<h1 class="main-header">🏪 Outlet Detail Checker</h1>', unsafe_allow_html=True)
    
    # Sidebar for navigation
    st.sidebar.title("📋 Menu")
    menu = st.sidebar.radio(
        "Pilih Menu:",
        ["🔍 Cari Outlet", "📊 Dashboard", "🗺️ Peta Sebaran", "💾 Export Data"],
        index=0
    )
    
    # Load data lazily
    df_outlet = None
    df_rute = None
    df_quadran = None
    
    if menu == "🔍 Cari Outlet":
        st.header("🔍 Pencarian Outlet")
        st.info("Masukkan ID atau Nama Outlet untuk melihat detail lengkap")
        
        # Search inputs
        col1, col2 = st.columns([3, 1])
        with col1:
            search_query = st.text_input(
                "Cari Outlet (ID / Nama)",
                placeholder="Ketik ID atau nama outlet...",
                label_visibility="collapsed"
            )
        with col2:
            search_type = st.selectbox(
                "Tipe Pencarian",
                ["contains", "exact", "fuzzy"],
                format_func=lambda x: {"contains": "Contains (Partial)", "exact": "Exact Match", "fuzzy": "Fuzzy Match"}[x]
            )
        
        if search_query:
            with st.spinner('Mencari outlet...'):
                df_outlet = get_outlet_data()
                
                if df_outlet is not None:
                    results = search_outlet(search_query, df_outlet, search_type)
                    
                    if len(results) == 0:
                        st.warning("❌ Outlet tidak ditemukan. Coba kata kunci lain atau tipe pencarian berbeda.")
                    elif len(results) > 20:
                        st.warning(f"⚠️ Ditemukan {len(results)} outlet. Tampilkan 20 pertama.")
                        results = results.head(20)
                    else:
                        st.success(f"✅ Ditemukan {len(results)} outlet")
                    
                    # Display results
                    for idx, (_, outlet) in enumerate(results.iterrows()):
                        with st.expander(f"🏪 {outlet.get('NAMA_PELANGGAN', 'N/A')} - {outlet.get('ID_PELANGGAN', 'N/A')}", expanded=(idx==0)):
                            col1, col2 = st.columns([2, 1])
                            
                            with col1:
                                st.subheader("📋 Informasi Outlet")
                                st.markdown(f"""
                                - **ID Pelanggan:** `{outlet.get('ID_PELANGGAN', 'N/A')}`
                                - **Nama:** {outlet.get('NAMA_PELANGGAN', 'N/A')}
                                - **Alamat:** {outlet.get('ALAMAT', 'N/A')}
                                - **Kelurahan:** {outlet.get('KELURAHAN', 'N/A')}
                                - **Kecamatan:** {outlet.get('KECAMATAN', 'N/A')}
                                - **Kab/Kota:** {outlet.get('KAB_KOT', 'N/A')}
                                - **Provinsi:** {outlet.get('PROVINSI', 'N/A')}
                                """)
                                
                                st.subheader("📞 Kontak")
                                st.markdown(f"""
                                - **Kontak Person:** {outlet.get('KONTAK', 'N/A')}
                                - **Telepon:** {outlet.get('TELEPON', 'N/A')}
                                """)
                                
                                st.subheader("💼 Bisnis")
                                st.markdown(f"""
                                - **Status:** {outlet.get('STATUS_PELANGGAN', 'N/A')}
                                - **Segmentasi:** {outlet.get('SEGMENTASI', 'N/A')}
                                - **Kredit Limit:** Rp {outlet.get('KREDIT_LIMIT', 0):,.0f}
                                """)
                            
                            with col2:
                                # Map
                                if pd.notna(outlet.get('Latitude')) and pd.notna(outlet.get('Longitude')):
                                    st.subheader("📍 Lokasi")
                                    single_outlet = pd.DataFrame([outlet])
                                    m = create_map(
                                        single_outlet,
                                        center_lat=outlet['Latitude'],
                                        center_lon=outlet['Longitude'],
                                        zoom=15
                                    )
                                    st_folium(m, width=400, height=300)
                                    
                                    # Distance calculator
                                    st.subheader("📏 Hitung Jarak")
                                    user_lat = st.number_input(
                                        "Latitude Anda",
                                        value=-6.2088,
                                        format="%.6f",
                                        key=f"user_lat_{idx}"
                                    )
                                    user_lon = st.number_input(
                                        "Longitude Anda",
                                        value=106.8456,
                                        format="%.6f",
                                        key=f"user_lon_{idx}"
                                    )
                                    
                                    if st.button("Hitung Jarak", key=f"calc_dist_{idx}"):
                                        distance = calculate_distance(
                                            user_lat, user_lon,
                                            outlet['Latitude'], outlet['Longitude']
                                        )
                                        if distance:
                                            st.metric("Jarak", f"{distance} km")
                                else:
                                    st.info("📍 Koordinat tidak tersedia")
                            
                            # Route info
                            st.subheader("🚚 Informasi Rute")
                            df_rute_temp = get_rute_data()
                            if df_rute_temp is not None:
                                routes = get_route_info(outlet.get('ID_PELANGGAN'), df_rute_temp)
                                if len(routes) > 0:
                                    st.dataframe(routes, use_container_width=True)
                                else:
                                    st.info("Tidak ada informasi rute untuk outlet ini")
                            else:
                                st.info("Data rute belum dimuat")
                            
                            # Quadran
                            st.subheader("🎯 Kuadran")
                            df_quadran_temp = get_quadran_data()
                            quadran = determine_quadran(
                                outlet.get('KELURAHAN'),
                                outlet.get('KECAMATAN'),
                                df_quadran_temp
                            )
                            st.metric("Kuadran", quadran)
        
        else:
            st.info("👆 Masukkan kata kunci pencarian di atas")
    
    elif menu == "📊 Dashboard":
        st.header("📊 Dashboard Analitik Outlet")
        
        with st.spinner('Memuat data untuk dashboard...'):
            df_outlet = get_outlet_data()
            
            if df_outlet is not None:
                # Metrics
                total_outlets = len(df_outlet)
                with_coords = df_outlet[pd.notna(df_outlet['Latitude']) & pd.notna(df_outlet['Longitude'])]
                num_with_coords = len(with_coords)
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total Outlet", f"{total_outlets:,}")
                col2.metric("Dengan Koordinat", f"{num_with_coords:,}")
                col3.metric("% Dengan Koordinat", f"{(num_with_coords/total_outlets*100):.1f}%")
                
                if 'KREDIT_LIMIT' in df_outlet.columns:
                    avg_kredit = df_outlet['KREDIT_LIMIT'].mean()
                    col4.metric("Avg Kredit Limit", f"Rp {avg_kredit:,.0f}")
                
                # Charts
                st.subheader("📈 Distribusi Status Pelanggan")
                if 'STATUS_PELANGGAN' in df_outlet.columns:
                    status_counts = df_outlet['STATUS_PELANGGAN'].value_counts().head(10)
                    fig = px.pie(values=status_counts.values, names=status_counts.index, hole=0.4)
                    st.plotly_chart(fig, use_container_width=True)
                
                st.subheader("📊 Distribusi Segmentasi")
                if 'SEGMENTASI' in df_outlet.columns:
                    seg_counts = df_outlet['SEGMENTASI'].value_counts().head(10)
                    fig = px.bar(x=seg_counts.index, y=seg_counts.values, labels={'x': 'Segmentasi', 'y': 'Jumlah'})
                    st.plotly_chart(fig, use_container_width=True)
                
                st.subheader("🏙️ Top 10 Kab/Kota")
                if 'KAB_KOT' in df_outlet.columns:
                    city_counts = df_outlet['KAB_KOT'].value_counts().head(10)
                    fig = px.bar(x=city_counts.values, y=city_counts.index, orientation='h', labels={'x': 'Jumlah', 'y': 'Kab/Kota'})
                    st.plotly_chart(fig, use_container_width=True)
                
                st.subheader("💰 Distribusi Kredit Limit")
                if 'KREDIT_LIMIT' in df_outlet.columns:
                    fig = px.histogram(df_outlet['KREDIT_LIMIT'], nbins=50, title='Histogram Kredit Limit')
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.error("Gagal memuat data")
    
    elif menu == "🗺️ Peta Sebaran":
        st.header("🗺️ Peta Sebaran Outlet")
        
        df_outlet = get_outlet_data()
        
        if df_outlet is not None:
            # Filter outlets with coordinates
            outlets_with_coords = df_outlet[pd.notna(df_outlet['Latitude']) & pd.notna(df_outlet['Longitude'])]
            
            st.info(f"Menampilkan {min(len(outlets_with_coords), 100)} dari {len(outlets_with_coords)} outlet dengan koordinat")
            
            m = create_map(outlets_with_coords.head(100))
            st_folium(m, width=1200, height=600)
    
    elif menu == "💾 Export Data":
        st.header("💾 Export Data Outlet")
        
        df_outlet = get_outlet_data()
        
        if df_outlet is not None:
            st.subheader("📥 Download Data")
            
            export_option = st.selectbox(
                "Pilih data yang akan diexport:",
                ["Semua Outlet", "Outlet dengan Koordinat", "Outlet Aktif"]
            )
            
            if export_option == "Semua Outlet":
                df_export = df_outlet
            elif export_option == "Outlet dengan Koordinat":
                df_export = df_outlet[pd.notna(df_outlet['Latitude']) & pd.notna(df_outlet['Longitude'])]
            else:
                df_export = df_outlet[df_outlet['STATUS_PELANGGAN'].astype(str).str.contains('AKTIF', na=False)]
            
            st.write(f"Preview ({len(df_export)} records):")
            st.dataframe(df_export.head(), use_container_width=True)
            
            # Create Excel file
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_export.to_excel(writer, index=False, sheet_name='Outlet Data')
            
            st.download_button(
                label="📥 Download Excel",
                data=buffer.getvalue(),
                file_name=f"outlet_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.ms-excel"
            )

if __name__ == "__main__":
    main()
