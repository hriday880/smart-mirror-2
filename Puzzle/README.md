# PuzzleCam — Gesture Capture

App de fotomatón controlada por gestos manuales que corre completamente en el navegador. Sin instalación, sin backend, sin dependencias que instalar.

---

## **DESCRIPCIÓN**

PuzzleCam captura una foto usando las manos como "marco", la convierte en un rompecabezas 3x3 con efecto fotográfico en blanco y negro, y permite armarlo usando gestos de pinch. Al completarlo, se guarda en una tira de fotos descargable.

---

## **REQUISITOS DEL SISTEMA**

- **Navegador:** Chrome o Edge (recomendado), Firefox
- **Hardware:** Cámara web
- **Conexión a internet:** Requerida para cargar el modelo de MediaPipe (~10MB, solo la primera vez)
- **Servidor local:** Requerido para ejecutar la app (no se puede abrir como archivo directamente)

---

## **INSTALACIÓN Y CONFIGURACIÓN**

### 1. Clonar el repositorio

```bash
git clone https://github.com/mishu006/Puzzle.git
cd Puzzle
```

### 2. Levantar el servidor local

**Opci��n recomendada:** doble clic en `Start_Puzzle.command`
(abre el servidor y el navegador autom��ticamente).

**Opci��n manual:**

```bash
node server.js
```

> ������ **Importante:** la app DEBE servirse desde este servidor (`localhost:3000`),
> no desde VS Code Live Server ni abriendo `index.html` directamente.
> El guardado de fotos funciona v��a `/api/upload`, que solo existe en este
> servidor Node. Si la app se sirve de otra forma, ver��s una advertencia al
> iniciar y el guardado fallar�� al completar el puzzle.

### 3. Abrir en el navegador

`http://localhost:3000`

### 3. Abrir en el navegador

```
http://localhost:5500
```

Permite el acceso a la cámara cuando el navegador lo solicite.

---

## **ESTRUCTURA DEL PROYECTO**

```
Puzzle/
├── index.html        # Punto de entrada de la app
├── app.js            # Lógica completa (tracking, puzzle, galería)
├── css/
│   └── styles.css    # Estilos y layout
└── .gitignore
```

---

## **GESTOS DE CONTROL**

| Gesto | Acción |
|---|---|
| Ambas manos haciendo pinch | Congelar el área y comenzar cuenta regresiva |
| Una mano haciendo pinch sobre una pieza | Arrastrar la pieza del puzzle |
| Puño cerrado (mantener) | Guardar puzzle completado / Reiniciar tablero |

---

## **LÓGICA DE LA APLICACIÓN**

1. Muestra ambas manos a la cámara y haz pinch para definir el recuadro de captura
2. Mantén el pinch durante la cuenta regresiva — la foto se toma automáticamente
3. La foto se divide en un puzzle 3x3 con filtro de fotomatón en blanco y negro
4. Reorganiza las piezas con gestos de pinch
5. Al completarlo, cierra el puño para guardar en la tira con animación de fragmentación
6. Descarga la tira completa cuando tengas 3 puzzles guardados

---

## **STACK TECNOLÓGICO**

- **[MediaPipe Tasks Vision](https://developers.google.com/mediapipe)** `v0.10.14` — detección de landmarks de la mano
- **qrcodejs** — generación de códigos QR (incluida localmente en `vendor/qrcode.min.js`, sin depender de CDN)
- **Canvas 2D API** — renderizado, piezas del puzzle, efecto fotomatón
- **JavaScript (ES Modules)** — sin frameworks
- **CSS Custom Properties** — theming y layout

Todas las dependencias externas se cargan por CDN. No se requiere ninguna instalación adicional.

---

## **GUIA DE SOLUCION DE PROBLEMAS**

### **"Upload failed" / no se puede guardar la foto**

La p��gina se sirve desde un servidor equivocado: Live Server de VS Code,
otro puerto, o `index.html` abierto directamente desde el Finder.
Cierra esa pesta��a y abre la app desde `http://localhost:3000`
(doble clic en `Start_Puzzle.command`). La app tambi��n muestra una
advertencia al iniciar si no detecta el servidor.

### **La cámara no enciende**

Verifica que ninguna otra aplicación (Teams, Zoom, Discord, etc.) esté usando la cámara en segundo plano.

### **La app no carga el modelo**

Verifica tu conexión a internet. El modelo de MediaPipe (~10MB) se descarga desde `storage.googleapis.com` y el runtime desde `cdn.jsdelivr.net`. Si alguno de esos dominios está bloqueado en tu red, la app no podrá iniciar.

### **La app muestra pantalla negra**

Asegúrate de estar abriendo la app desde un servidor local (HTTP), no directamente como archivo desde el explorador de archivos.

### **El gesto de pinch no se detecta**

Asegúrate de tener buena iluminación y que ambas manos sean visibles para la cámara. Acerca más el índice y el pulgar hasta que el punto amarillo en pantalla se active.

---

## **COMPATIBILIDAD DE NAVEGADORES**

| Navegador | Soporte |
|---|---|
| Chrome / Edge | Recomendado |
| Firefox | Compatible |
| Safari | Limitado (puede requerir permisos adicionales) |
| Movil | Limitado (recomendado en escritorio) |

---

## **LICENCIA**

MIT — libre para usar, modificar y compartir.
