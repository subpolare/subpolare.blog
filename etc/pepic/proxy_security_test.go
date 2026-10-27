package handler

import (
	"bytes"
	"image"
	"image/jpeg"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/labstack/echo/v4"
	"github.com/vas3k/pepic/pepic/config"
	"github.com/vas3k/pepic/pepic/processing"
	"github.com/vas3k/pepic/pepic/storage"
	"github.com/vas3k/pepic/pepic/utils"
)

func TestResizeErrorsAndLegitimateImage(t *testing.T) {
	previous := config.App
	defer func() { config.App = previous }()
	config.App.Global.FileTreeSplitChars = 3
	config.App.Images.OriginalLength = 1800
	config.App.Images.LiveResize = true
	config.App.Images.JPEGQuality = 95
	root := t.TempDir()
	h := &PepicHandler{Storage: storage.NewStorage(storage.NewFileSystemBackend(root)),
		Processing: processing.Processing{Image: processing.NewImageBackend()}}
	e := echo.New()
	e.GET("/:length/:name", h.GetResizedFile)
	e.GET("/:name", h.GetOriginalFile)
	missing := strings.Repeat("a", 64) + ".jpg"
	for route, want := range map[string]int{
		"/480/" + missing: 404, "/0960/" + missing: 404, "/1440/" + missing: 404,
		"/full/" + missing: 404, "/2000/" + missing: 404,
		"/481/" + missing: 400, "/-1/" + missing: 400, "/0/" + missing: 400,
	} {
		r := httptest.NewRecorder()
		e.ServeHTTP(r, httptest.NewRequest("GET", route, nil))
		if r.Code != want {
			t.Fatalf("%s: got %d want %d", route, r.Code, want)
		}
	}
	name := strings.Repeat("b", 64) + ".jpg"
	var original bytes.Buffer
	if err := jpeg.Encode(&original, image.NewRGBA(image.Rect(0, 0, 1200, 900)), nil); err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(root, "orig", utils.CanonizeFileName(name))
	if err := os.MkdirAll(filepath.Dir(file), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(file, original.Bytes(), 0644); err != nil {
		t.Fatal(err)
	}
	r := httptest.NewRecorder()
	e.ServeHTTP(r, httptest.NewRequest("GET", "/480/"+name, nil))
	if r.Code != 200 {
		t.Fatalf("valid resize: %d %s", r.Code, r.Body.String())
	}
	dim, err := jpeg.DecodeConfig(bytes.NewReader(r.Body.Bytes()))
	if err != nil || dim.Width != 480 || dim.Height != 360 {
		t.Fatalf("dimensions: %+v %v", dim, err)
	}
	for _, route := range []string{"/" + name, "/full/" + name} {
		r = httptest.NewRecorder()
		e.ServeHTTP(r, httptest.NewRequest("GET", route, nil))
		if r.Code != 200 || !bytes.Equal(r.Body.Bytes(), original.Bytes()) {
			t.Fatalf("original changed: %s", route)
		}
	}
	// Saturation rejects new work but still serves prepared derivatives.
	resizeSlots <- struct{}{}
	resizeSlots <- struct{}{}
	defer func() { <-resizeSlots; <-resizeSlots }()
	for route, want := range map[string]int{"/960/" + name: 503, "/480/" + name: 200} {
		r = httptest.NewRecorder()
		e.ServeHTTP(r, httptest.NewRequest("GET", route, nil))
		if r.Code != want {
			t.Fatalf("busy %s: %d", route, r.Code)
		}
	}
}
