import os
import snowflake.connector
import pandas as pd
import warnings
import json
import webbrowser
from dotenv import load_dotenv

warnings.filterwarnings('ignore')
load_dotenv()

URL_GOOGLE_SHEETS = "https://script.google.com/macros/s/AKfycbw3PIzMFzFEefukmvP6GjiD1UOvE5Uf3DdXqO-J03P4E-6X1Dp3568I6rSphGVGFk6wBg/exec" 

print("🚀 Iniciando Motor Turbo IA...")

# --- 1. CONEXIÓN A SNOWFLAKE ---
try:
    conn = snowflake.connector.connect(
        user=os.getenv('SNOWFLAKE_USER'),
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        role=os.getenv('SNOWFLAKE_ROLE'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
        database=os.getenv('SNOWFLAKE_DATABASE'),
        schema=os.getenv('SNOWFLAKE_SCHEMA'),
        authenticator='externalbrowser'
    )

    query = """
    WITH SUMMARY_STOCK AS (
        SELECT PRODUCT_ID, SUM(STOCK_UNITS) AS TOTAL_STOCK_TODAY
        FROM RP_SILVER_DB_PROD.TURBO_CORE.GLOBAL_CLOSING_INVENTORY_CURRENT
        GROUP BY 1
    ),
    SUMMARY_SALES AS (
        SELECT EAN, SUM(UNITS) AS UNITS_SOLD_LAST_MONTH, SUM(TOTAL_PRICE_W_IVA) AS GROSS_SALES_LAST_MONTH
        FROM RP_SILVER_DB_PROD.TURBO_CORE.GLOBAL_ORDER_DISCOUNTS
        WHERE COUNTRY = 'MX' AND VERTICAL_SUB_GROUP = 'TURBO'
          AND CREATED_AT >= DATEADD(month, -1, CURRENT_DATE())
        GROUP BY 1
    )
    SELECT
        cat.PRODUCT_NAME,
        cat.CATEGORY_NAME,
        cat.EAN,
        COALESCE(stk.TOTAL_STOCK_TODAY, 0) AS STOCK_ACTUAL,
        COALESCE(sls.GROSS_SALES_LAST_MONTH, 0) AS VENTA_BRUTA_30D
    FROM RP_SILVER_DB_PROD.TURBO_CORE.MX_CATALOG_DATASCIENCE AS cat
    INNER JOIN SUMMARY_STOCK AS stk ON cat.SYNC_ID = stk.PRODUCT_ID
    LEFT JOIN SUMMARY_SALES AS sls ON cat.EAN = sls.EAN
    WHERE cat.IS_CATALOG = 'TRUE' AND cat.COUNTRY = 'MX'
    ORDER BY VENTA_BRUTA_30D DESC
    LIMIT 5000;
    """
    print("❄️ Descargando inventario de Snowflake...")
    df_catalogo = pd.read_sql(query, conn)
    conn.close()
except Exception as e:
    print(f"⚠️ Aviso: No se pudo conectar a Snowflake. Usando datos vacíos. Error: {e}")
    df_catalogo = pd.DataFrame(columns=['PRODUCT_NAME', 'CATEGORY_NAME', 'STOCK_ACTUAL', 'VENTA_BRUTA_30D'])

# --- 2. GENERANDO ASSORTMENT ---
df_disponible = df_catalogo[df_catalogo['STOCK_ACTUAL'] > 0].copy()
if not df_disponible.empty:
    df_disponible['CAT_UP'] = df_disponible['CATEGORY_NAME'].astype(str).str.upper().str.strip()

reglas_ia_seasonals = {
    's-mundial': [('🍻 Hidratación Campeones', ['CERVEZAS Y SIDRAS']), ('🥃 Licores Tiempo Extra', ['LICORES Y APERITIVOS']), ('🥨 Estadio del Sabor', ['SNACKS Y CONFITERÍA', 'SNACKS']), ('🥤 Gradería Familiar', ['GASEOSAS', 'AGUAS'])],
    's-backtoschool': [('🧃 Jugos y Lácteos', ['JUGOS', 'LÁCTEOS', 'BEBIDAS N/ALC']), ('🍪 Snacks para el Recreo', ['SNACKS Y CONFITERÍA', 'SNACKS']), ('🥪 Para el Sándwich', ['CHARCUTERÍA', 'PANADERÍA']), ('🍎 Frutas de Lunch', ['FRUTAS Y VERDURAS'])],
    's-rappibday': [('🥳 Chelas de Aniversario', ['CERVEZAS Y SIDRAS']), ('🥃 Licores de Fiesta', ['LICORES Y APERITIVOS', 'VINOS']), ('🥤 Feria de Aguas', ['AGUAS', 'GASEOSAS']), ('🥨 Botanas Festivas', ['SNACKS Y CONFITERÍA'])],
    's-patrias': [('🌵 El Rincón del Tequila', ['LICORES Y APERITIVOS']), ('🍻 Chelas para el Grito', ['CERVEZAS Y SIDRAS']), ('🥩 Asado Patrio', ['CHARCUTERÍA', 'CARNES']), ('🌶️ Botanas Picosas', ['SNACKS Y CONFITERÍA'])],
    's-muertos': [('🕯️ Para la Ofrenda (Dulces)', ['SNACKS Y CONFITERÍA', 'PANADERÍA']), ('🥃 El Trago del Recuerdo', ['LICORES Y APERITIVOS']), ('🍻 Brindis al Más Allá', ['CERVEZAS Y SIDRAS']), ('🥤 Bebidas de Compañía', ['GASEOSAS', 'AGUAS'])],
    's-buenfin': [('🥃 Promos en Licores', ['LICORES Y APERITIVOS', 'VINOS']), ('🍻 Cervezas en Oferta', ['CERVEZAS Y SIDRAS']), ('🥨 Botanas Grandes', ['SNACKS Y CONFITERÍA']), ('🔋 Cuidado Personal', ['CUIDADO PERSONAL', 'FARMACIA'])],
    's-navidad': [('🍾 Brindis (Vinos y Licores)', ['VINOS', 'LICORES Y APERITIVOS']), ('🍻 Posada Cervecera', ['CERVEZAS Y SIDRAS']), ('🧀 Tabla de Quesos y Carnes', ['CHARCUTERÍA']), ('🍬 Dulces Fiestas', ['SNACKS Y CONFITERÍA'])]
}

base_de_datos_final = {}
for id_seasonal, reglas_corredores in reglas_ia_seasonals.items():
    lista_productos = []
    if not df_disponible.empty:
        for nombre_corredor, categorias_validas in reglas_corredores:
            subset = df_disponible[df_disponible['CAT_UP'].isin(categorias_validas)].head(30)
            for _, row in subset.iterrows():
                lista_productos.append({
                    'corredor': nombre_corredor,
                    'producto': row['PRODUCT_NAME'],
                    'stock': int(row['STOCK_ACTUAL']),
                    'ventas': f"${int(row['VENTA_BRUTA_30D']):,}"
                })
    base_de_datos_final[id_seasonal] = lista_productos

# --- 3. LEYENDO Y FILTRANDO GOOGLE SHEETS ---
print("📊 Conectando a Google Sheets para cruzar fechas de Descuentos...")
resumen_descuentos = {}

try:
    df_promos = pd.read_csv(URL_GOOGLE_SHEETS)
    columnas_limpias = [str(c).strip().upper() for c in df_promos.columns]
    columnas_limpias[-1] = 'CATEGORIA_REAL'
    df_promos.columns = columnas_limpias

    if 'DESCUENTO' in df_promos.columns:
        col_desc = df_promos['DESCUENTO'].iloc[:, 0] if isinstance(df_promos['DESCUENTO'], pd.DataFrame) else df_promos['DESCUENTO']
        df_promos['VALOR_DESC'] = col_desc.astype(str).str.replace('%', '', regex=False).str.strip()
        df_promos['VALOR_DESC'] = pd.to_numeric(df_promos['VALOR_DESC'], errors='coerce').fillna(0)
    else:
        df_promos['VALOR_DESC'] = 0

    if 'INICIO' in df_promos.columns:
        col_ini = df_promos['INICIO'].iloc[:, 0] if isinstance(df_promos['INICIO'], pd.DataFrame) else df_promos['INICIO']
        df_promos['FECHA_INICIO'] = pd.to_datetime(col_ini, errors='coerce', utc=True).dt.tz_localize(None)
    else:
        df_promos['FECHA_INICIO'] = pd.to_datetime('2026-01-01')

    if 'FIN' in df_promos.columns:
        col_fin = df_promos['FIN'].iloc[:, 0] if isinstance(df_promos['FIN'], pd.DataFrame) else df_promos['FIN']
        df_promos['FECHA_FIN'] = pd.to_datetime(col_fin, errors='coerce', utc=True).dt.tz_localize(None)
    else:
        df_promos['FECHA_FIN'] = pd.to_datetime('2026-12-31')

    def clasificar_promo(val):
        if val >= 30: return 'Bueno'
        elif val >= 15: return 'Regular'
        else: return 'BAU'
    
    df_promos['TIPO'] = df_promos['VALOR_DESC'].apply(clasificar_promo)

    fechas_seasonals = {
        's-mundial': ('2026-06-01', '2026-07-19'),
        's-rappibday': ('2026-08-01', '2026-08-15'),
        's-backtoschool': ('2026-07-20', '2026-08-31'),
        's-patrias': ('2026-09-01', '2026-09-16'),
        's-muertos': ('2026-10-15', '2026-11-02'),
        's-buenfin': ('2026-11-01', '2026-11-30'),
        's-navidad': ('2026-12-01', '2026-12-31')
    }

    for sid, (start_str, end_str) in fechas_seasonals.items():
        seasonal_start = pd.to_datetime(start_str)
        seasonal_end = pd.to_datetime(end_str)
        
        mask_fechas = (df_promos['FECHA_INICIO'] <= seasonal_end) & (df_promos['FECHA_FIN'] >= seasonal_start)
        df_filtrado = df_promos[mask_fechas]

        if df_filtrado.empty:
            resumen_descuentos[sid] = []
            continue

        agrupado = pd.crosstab(df_filtrado['CATEGORIA_REAL'], df_filtrado['TIPO']).reset_index()
        
        for col in ['Bueno', 'Regular', 'BAU']:
            if col not in agrupado.columns:
                agrupado[col] = 0

        lista_bu = []
        for _, row in agrupado.iterrows():
            lista_bu.append({
                'BU': str(row['CATEGORIA_REAL']).upper(),
                'Bueno': int(row['Bueno']),
                'Regular': int(row['Regular']),
                'BAU': int(row['BAU']),
                'Total': int(row['Bueno']) + int(row['Regular']) + int(row['BAU'])
            })
        
        lista_bu = sorted(lista_bu, key=lambda x: x['Total'], reverse=True)
        resumen_descuentos[sid] = lista_bu

    print("✅ ¡Cruce de fechas de Google Sheets completado exitosamente!")
except Exception as e:
    import traceback
    print("⚠️ Ocurrió un error leyendo el Sheets. Aquí están los detalles:")
    traceback.print_exc()
    for key in reglas_ia_seasonals.keys():
        resumen_descuentos[key] = []

datos_json = json.dumps({'assortment': base_de_datos_final, 'resumen_promos': resumen_descuentos})

# --- 4. ARMADO DEL DASHBOARD VISUAL ---
html_content = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Turbo Strategy Dashboard MX</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
    <style>
        body { font-family: 'Inter', sans-serif; }
        .scrollbar-hide::-webkit-scrollbar { display: none; }
        .scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }
    </style>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">

    <div id="pantalla-login" class="flex min-h-screen items-center justify-center bg-gray-950 px-4">
        <div class="w-full max-w-md space-y-6 bg-gray-900 p-8 rounded-2xl border border-gray-800 shadow-2xl text-center">
            <div>
                <h2 class="text-3xl font-extrabold text-white text-orange-500">Acceso Restringido</h2>
                <p class="text-sm text-gray-400 mt-2">Ingresa tu correo corporativo para recibir tu clave de acceso.</p>
            </div>
            
            <div id="form-email" class="space-y-4">
                <input id="input-email" type="email" placeholder="nombre@tuempresa.com" 
                       class="w-full p-3 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-orange-500">
                <button onclick="enviarTokenMagico()" class="w-full bg-orange-600 hover:bg-orange-500 text-white font-bold py-3 rounded-lg transition-all shadow-[0_0_15px_rgba(234,88,12,0.3)]">
                    Solicitar Código de Acceso
                </button>
            </div>

            <div id="form-token" class="space-y-4 hidden">
                <p class="text-xs text-green-400 font-medium">¡Código enviado! Revisa tu bandeja de entrada.</p>
                <input id="input-token" type="text" placeholder="Introduce el código de 6 dígitos" 
                       class="w-full p-3 bg-gray-800 border border-gray-700 rounded-lg text-center font-mono text-xl tracking-widest text-white focus:outline-none focus:border-orange-500">
                <button onclick="verificarToken()" class="w-full bg-green-600 hover:bg-green-500 text-white font-bold py-3 rounded-lg transition-all">
                    Verificar y Entrar 
                </button>
            </div>
            <p id="mensaje-error" class="text-xs text-red-500 font-semibold hidden"></p>
        </div>
    </div>

    <div id="contenido-dashboard" class="flex hidden">
        <aside class="w-80 bg-gray-900 h-screen sticky top-0 p-6 border-r border-gray-800 overflow-y-auto scrollbar-hide">
            <div class="flex justify-between items-center mb-6">
                <h2 class="text-orange-500 font-bold text-xl flex items-center gap-2">🗓️ Seasonals MX</h2>
                <button onclick="cerrarSesion()" class="text-xs text-gray-500 hover:text-red-400 transition-colors">Cerrar Sesión</button>
            </div>
            <div class="space-y-3 pb-10">
                <div id="s-mundial" onclick="cambiarSeasonal('🏆 Final Mundial 2026', 's-mundial')" class="seasonal-item cursor-pointer p-3 bg-gray-800 rounded border-l-4 border-orange-500 transition-colors">
                    <p class="text-xs text-gray-400">JUNIO - JULIO</p>
                    <p class="font-bold">🏆 Final Mundial</p>
                </div>
                <div id="s-rappibday" onclick="cambiarSeasonal('🎉 Rappi Birthday', 's-rappibday')" class="seasonal-item cursor-pointer p-3 bg-gray-800/50 hover:bg-gray-800 rounded border-l-4 border-gray-600 transition-colors">
                    <p class="text-xs text-gray-400">AGOSTO</p>
                    <p class="font-bold">🎉 Rappi Birthday</p>
                </div>
                <div id="s-backtoschool" onclick="cambiarSeasonal('🎒 Back to School', 's-backtoschool')" class="seasonal-item cursor-pointer p-3 bg-gray-800/50 hover:bg-gray-800 rounded border-l-4 border-gray-600 transition-colors">
                    <p class="text-xs text-gray-400">AGOSTO</p>
                    <p class="font-bold">🎒 Back to School</p>
                </div>
                <div id="s-patrias" onclick="cambiarSeasonal('🇲🇽 Fiestas Patrias', 's-patrias')" class="seasonal-item cursor-pointer p-3 bg-gray-800/50 hover:bg-gray-800 rounded border-l-4 border-gray-600 transition-colors">
                    <p class="text-xs text-gray-400">SEPTIEMBRE</p>
                    <p class="font-bold">🇲🇽 Fiestas Patrias</p>
                </div>
                <div id="s-muertos" onclick="cambiarSeasonal('💀 Día de Muertos', 's-muertos')" class="seasonal-item cursor-pointer p-3 bg-gray-800/50 hover:bg-gray-800 rounded border-l-4 border-gray-600 transition-colors">
                    <p class="text-xs text-gray-400">OCTUBRE - NOVIEMBRE</p>
                    <p class="font-bold">💀 Día de Muertos</p>
                </div>
                <div id="s-buenfin" onclick="cambiarSeasonal('🛒 Buen Fin', 's-buenfin')" class="seasonal-item cursor-pointer p-3 bg-gray-800/50 hover:bg-gray-800 rounded border-l-4 border-gray-600 transition-colors">
                    <p class="text-xs text-gray-400">NOVIEMBRE</p>
                    <p class="font-bold">🛒 Buen Fin</p>
                </div>
                <div id="s-navidad" onclick="cambiarSeasonal('🎄 Navidad & Fin de Año', 's-navidad')" class="seasonal-item cursor-pointer p-3 bg-gray-800/50 hover:bg-gray-800 rounded border-l-4 border-gray-600 transition-colors">
                    <p class="text-xs text-gray-400">DICIEMBRE</p>
                    <p class="font-bold">🎄 Navidad & Fin de Año</p>
                </div>
            </div>
        </aside>

        <main class="flex-1 p-8">
            <header class="flex justify-between items-center mb-6">
                <div>
                    <h1 class="text-4xl font-extrabold text-white">Estrategia Turbo <span class="text-orange-500">Live</span></h1>
                    <p class="text-gray-400">Optimización de surtido basada en inventario real y demandas programadas.</p>
                </div>
                <div class="text-right">
                    <p class="text-sm text-gray-500">Autenticado corporativo</p>
                    <p class="font-mono text-green-400">Acceso Seguro ✅</p>
                </div>
            </header>

            <div class="flex justify-between items-center mb-6 bg-gray-900 p-4 rounded-xl border border-gray-800 shadow-2xl">
                <div>
                    <span class="text-sm text-gray-400">Seasonal Seleccionado:</span>
                    <span id="texto-seasonal" class="ml-2 font-bold text-white text-lg">🏆 Final Mundial 2026</span>
                </div>
                <button id="btnGenerar" onclick="mostrarAssortment()" class="bg-orange-600 hover:bg-orange-500 text-white font-bold py-3 px-8 rounded-full transition-all shadow-[0_0_20px_rgba(234,88,12,0.4)]">
                    ⚡ Extraer Data del Seasonal
                </button>
            </div>

            <div id="loader" class="hidden py-10 text-center">
                <div class="inline-block animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-orange-500 mb-4"></div>
                <p class="text-orange-500 animate-pulse font-bold text-xl">Procesando datos...</p>
            </div>

            <div id="contenedor-resultados" class="hidden">
                <div class="mb-8 bg-gray-900 p-5 rounded-xl border border-gray-800 shadow-lg">
                    <h3 class="text-orange-500 font-bold mb-1 flex items-center gap-2">📉 Resumen de Descuentos Activos por Categoría</h3>
                    <p class="text-xs text-gray-400 mb-4">SKUs programados durante el rango de fechas del evento. (Bueno ≥30%, Regular 15-29%, BAU <15%)</p>
                    <div class="overflow-hidden rounded-lg border border-gray-700">
                        <table class="w-full text-left text-sm text-gray-300">
                            <thead class="bg-gray-800 text-xs uppercase text-gray-400">
                                <tr>
                                    <th class="p-3">Categoría Real</th>
                                    <th class="p-3 text-center text-red-400">🔥 Bueno</th>
                                    <th class="p-3 text-center text-yellow-400">👍 Regular</th>
                                    <th class="p-3 text-center text-blue-400">🛒 BAU</th>
                                    <th class="p-3 text-right">Total SKUs</th>
                                </tr>
                            </thead>
                            <tbody id="cuerpoResumen" class="divide-y divide-gray-800">
                            </tbody>
                        </table>
                    </div>
                </div>

                <h3 class="text-orange-500 font-bold mb-3 flex items-center gap-2">📦 Propuesta de Surtido (Stock Real de Hoy)</h3>
                <div class="bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden shadow-2xl">
                    <div class="max-h-[400px] overflow-y-auto">
                        <table class="w-full text-left">
                            <thead class="bg-gray-800/90 sticky top-0 text-gray-400 uppercase text-xs backdrop-blur-sm z-10">
                                <tr>
                                    <th class="p-4">Corredor Temático</th>
                                    <th class="p-4">Producto</th>
                                    <th class="p-4 text-center">Ventas (30D)</th>
                                    <th class="p-4 text-right">Stock Real</th>
                                </tr>
                            </thead>
                            <tbody id="cuerpoTabla" class="divide-y divide-gray-800 text-sm">
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <script>
        // --- 1. CONFIGURACIÓN DE SUPABASE ---
        const SUPABASE_URL = "https://zemjpqzerbgiiprtkplu.supabase.co";
        const SUPABASE_ANON_KEY = "sb_publishable_Mh2EfA-XtLlPQF1385uz7g_W08dmU6F"; 
        
        const supabase = supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

        async function comprobarSesionActiva() {
            const { data: { session } } = await supabase.auth.getSession();
            if (session) {
                document.getElementById('pantalla-login').classList.add('hidden');
                document.getElementById('contenido-dashboard').classList.remove('hidden');
            }
        }

        async function enviarTokenMagico() {
            const email = document.getElementById('input-email').value;
            const errorBox = document.getElementById('mensaje-error');
            errorBox.classList.add('hidden');

            if(!email) return mostrarError("Por favor, introduce tu correo.");

            const { error } = await supabase.auth.signInWithOtp({ email: email });
            
            if (error) {
                mostrarError("Error al enviar código: " + error.message);
            } else {
                document.getElementById('form-email').classList.add('hidden');
                document.getElementById('form-token').classList.remove('hidden');
            }
        }

        async function verificarToken() {
            const email = document.getElementById('input-email').value;
            const token = document.getElementById('input-token').value;
            
            const { data, error } = await supabase.auth.verifyOtp({
                email: email,
                token: token,
                type: 'magiclink'
            });

            if (error) {
                mostrarError("Código incorrecto o vencido.");
            } else {
                document.getElementById('pantalla-login').classList.add('hidden');
                document.getElementById('contenido-dashboard').classList.remove('hidden');
            }
        }

        async function cerrarSesion() {
            await supabase.auth.signOut();
            window.location.reload();
        }

        function mostrarError(msg) {
            const box = document.getElementById('mensaje-error');
            box.innerText = msg;
            box.classList.remove('hidden');
        }

        // Ejecutar al cargar la página
        comprobarSesionActiva();

        // --- 2. LÓGICA DE DATOS DEL DASHBOARD ---
        const datosGenerales = DATO_JSON_AQUI;
        const baseDatosGlobal = datosGenerales.assortment;
        const basePromos = datosGenerales.resumen_promos;
        
        let seasonalActualId = 's-mundial';

        function cambiarSeasonal(nombre, idElemento) {
            seasonalActualId = idElemento;
            
            const items = document.querySelectorAll('.seasonal-item');
            items.forEach(item => {
                item.classList.remove('bg-gray-800', 'border-orange-500');
                item.classList.add('bg-gray-800/50', 'border-gray-600');
            });

            const elementoActivo = document.getElementById(idElemento);
            elementoActivo.classList.remove('bg-gray-800/50', 'border-gray-600');
            elementoActivo.classList.add('bg-gray-800', 'border-orange-500');

            document.getElementById('texto-seasonal').innerText = nombre;
            
            document.getElementById('contenedor-resultados').classList.add('hidden');
            document.getElementById('btnGenerar').classList.remove('hidden');
        }

        function mostrarAssortment() {
            const btn = document.getElementById('btnGenerar');
            const loader = document.getElementById('loader');
            const contenedor = document.getElementById('contenedor-resultados');
            const cuerpoResumen = document.getElementById('cuerpoResumen');
            const cuerpoTabla = document.getElementById('cuerpoTabla');

            btn.classList.add('hidden');
            loader.classList.remove('hidden');

            setTimeout(() => {
                loader.classList.add('hidden');
                contenedor.classList.remove('hidden');
                
                const promos = basePromos[seasonalActualId] || [];
                if(promos.length > 0) {
                    cuerpoResumen.innerHTML = promos.map(row => `
                        <tr class="hover:bg-gray-800/50 transition-colors">
                            <td class="p-3 font-bold text-gray-200">${row.BU}</td>
                            <td class="p-3 text-center text-red-400 font-semibold">${row.Bueno > 0 ? row.Bueno : '-'}</td>
                            <td class="p-3 text-center text-yellow-400 font-semibold">${row.Regular > 0 ? row.Regular : '-'}</td>
                            <td class="p-3 text-center text-blue-400 font-semibold">${row.BAU > 0 ? row.BAU : '-'}</td>
                            <td class="p-3 text-right font-mono text-gray-400">${row.Total}</td>
                        </tr>
                    `).join('');
                } else {
                    cuerpoResumen.innerHTML = `<tr><td colspan="5" class="p-4 text-center text-gray-500 italic">No se encontraron descuentos activos para el rango de fechas de este evento.</td></tr>`;
                }
                
                const surtido = baseDatosGlobal[seasonalActualId] || [];
                if(surtido.length > 0) {
                    cuerpoTabla.innerHTML = surtido.map(item => `
                        <tr class="hover:bg-gray-800/40 transition-colors">
                            <td class="p-4 font-bold text-orange-400/80">${item.corredor}</td>
                            <td class="p-4 text-gray-200">${item.producto}</td>
                            <td class="p-4 text-center text-gray-400">${item.ventas}</td>
                            <td class="p-4 text-right font-mono text-green-400">${item.stock.toLocaleString('en-US')} u.</td>
                        </tr>
                    `).join('');
                } else {
                    cuerpoTabla.innerHTML = `<tr><td colspan="4" class="p-4 text-center text-gray-500 italic">No se encontraron productos en stock.</td></tr>`;
                }

                document.getElementById('contenedor-resultados').scrollIntoView({ behavior: 'smooth', block: 'start' });

            }, 800); 
        }
    </script>
</body>
</html>
"""

html_content = html_content.replace("DATO_JSON_AQUI", datos_json)

ruta = os.path.abspath("dashboard_turbo_final.html")
with open(ruta, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"✅ ¡LISTO! Todo integrado y seguro. Abriendo el Dashboard Definitivo...")
webbrowser.open('file://' + ruta)