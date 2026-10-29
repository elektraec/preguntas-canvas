# Preguntas a Canvas

Web: **https://elektraec.github.io/preguntas-canvas/**

Convierte archivos CSV en paquetes QTI para importar en Canvas. Incluye una interfaz web en español, plantilla con seis tipos, validación, vista previa, puntos y retroalimentación.

## Uso

1. Descarga la plantilla desde la web y sustituye los ejemplos por tus preguntas.
2. Selecciona o arrastra el CSV (UTF-8, coma o punto y coma, hasta 10 MB).
3. Revisa el resumen y el título del cuestionario.
4. Elige Canvas QTI 1.2 o QTI 2.1 y genera el paquete.
5. Descarga el ZIP e impórtalo en un nuevo New Quiz: **Build / Construir → ⋯ → Importar contenido**.

Revisa el número de preguntas, las respuestas, puntos y feedback después de importar. La visibilidad del feedback depende también de los ajustes de resultados de Canvas. El importador puede reinterpretar contenido; la validación local no sustituye una prueba en el LMS.

## Tipos de pregunta

| Tipo | Respuesta |
|---|---|
| `mc` | Dos a cuatro opciones; una letra correcta, como `b`. |
| `ma` | Varias opciones correctas, como `a,c`. Se exportan reglas de todo o nada. |
| `tf` | `verdadero` o `falso`; las opciones se generan automáticamente. |
| `short` | Texto literal en `correcta`, con alternativas opcionales. |
| `blank` | Un marcador `{{respuesta}}` dentro del enunciado; respuesta de texto. |
| `essay` | Respuesta extensa, de corrección manual. |

Columnas de la plantilla:

```text
id,titulo,tipo,pregunta,a,b,c,d,correcta,respuestas_aceptadas,puntos,feedback,feedback_correcta,feedback_incorrecta,feedback_a,feedback_b,feedback_c,feedback_d
```

- `puntos`: número mayor que cero, con punto decimal; por defecto 1.
- `feedback`: explicación general; los demás campos permiten feedback por resultado y por opción.
- `respuestas_aceptadas`: lista JSON en una celda, por ejemplo `["Quito", "San Francisco de Quito"]`. Se aceptan sin distinguir mayúsculas, pero sí tildes y espacios.
- `id` y `titulo` son opcionales. Los identificadores, si se indican, deben ser únicos, comenzar con letra ASCII o `_` y usar letras ASCII, números, `_`, `.` o `-`.
- En ensayo deja vacíos `correcta`, alternativas, opciones y feedback de acierto/error; admite feedback general.
- La columna `correcta` debe existir, aunque su valor pueda estar vacío en ensayo o si se usan alternativas de texto.

Las plantillas anteriores siguen siendo válidas. Se recomienda indicar el tipo explícitamente.

## Privacidad y arquitectura

El motor Python corregido se ejecuta con **Pyodide 314.0.7** en un Web Worker. Los CSV, las respuestas y los ZIP se procesan en la memoria del navegador; no se suben a GitHub ni a un servidor de conversión. No hay cuentas, base de datos, telemetría ni almacenamiento persistente del banco.

La primera carga necesita Internet para descargar Pyodide desde jsDelivr y los archivos de la aplicación desde GitHub Pages. Esos servicios reciben las solicitudes habituales de visita, pero la aplicación no les envía el contenido de las preguntas. No se promete funcionamiento sin conexión.

La web usa exactamente el motor Python de este repositorio, incluidas las correcciones para el importador QTI 1.2 de Instructure: sin asignación de puntuación en condiciones `other`, y alternativas de texto en condiciones independientes. QTI 2.1 permanece disponible, aunque Canvas puede omitir su feedback.

## Desarrollo y verificación

Requisitos: Python 3.14 y Node.js 24. No hay dependencias npm de producción ni se requiere PySide6.

```sh
python -m unittest discover -s tests -v
npm run build
python -m http.server 8765 --directory public
```

Abre `http://localhost:8765`. La compilación copia únicamente los archivos web y los seis módulos Python necesarios a `public/`, y genera la plantilla desde el motor. `public/` no se guarda en Git.

Las pruebas verifican puntuación, feedback, respuestas alternativas, selección múltiple, ensayo manual, espacios en blanco, referencias del ZIP y las restricciones identificadas del importador de Canvas. No realizan importaciones reales en una instancia de Canvas.

## Publicación

GitHub Actions verifica las pruebas, prepara los archivos estáticos y publica únicamente `public/` en GitHub Pages al actualizar `main`. El repositorio no incluye ejecutables, entornos, pruebas históricas, ZIP de salida ni bancos reales.

## Referencias

- [Importar QTI en New Quizzes](https://community.instructure.com/en/kb/articles/661050-how-do-i-import-a-quiz-from-a-qti-package-in-new-quizzes)
- [Código del importador de opciones de Instructure](https://github.com/instructure/qti/blob/master/lib/qti/v1/models/interactions/choice_interaction.rb)
- [Código del importador de espacios en blanco](https://github.com/instructure/qti/blob/master/lib/qti/v1/models/interactions/fill_blank_interaction.rb)
- [Pyodide y Web Workers](https://pyodide.org/en/stable/usage/webworker.html)

Proyecto independiente de Canvas e Instructure.
