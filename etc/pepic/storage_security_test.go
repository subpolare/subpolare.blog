package storage

import (
	"errors"
	"os"
	"testing"

	"github.com/vas3k/pepic/pepic/config"
	"github.com/vas3k/pepic/pepic/entity"
)

func TestStorageErrorsReturnToCaller(t *testing.T) {
	previous := config.App
	defer func() { config.App = previous }()
	config.App.Global.FileTreeSplitChars = 3
	s := NewStorage(NewFileSystemBackend(t.TempDir()))
	file := &entity.ProcessingFile{Filename: "missing.jpg"}
	if err := s.ReadFileBytes(file, "orig"); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("missing read should return not-exist: %v", err)
	}
	rootFile := t.TempDir() + "/not-a-directory"
	if err := os.WriteFile(rootFile, []byte("file"), 0600); err != nil {
		t.Fatal(err)
	}
	s = NewStorage(NewFileSystemBackend(rootFile))
	file.Bytes = []byte("image")
	if err := s.StoreFile(file, "orig"); err == nil {
		t.Fatal("write failure must be returned")
	}
	// A later ordinary operation must still succeed in this same process.
	s = NewStorage(NewFileSystemBackend(t.TempDir()))
	if err := s.StoreFile(file, "orig"); err != nil {
		t.Fatal(err)
	}
	if err := s.ReadFileBytes(file, "orig"); err != nil {
		t.Fatal(err)
	}
}
