package main

import (
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"

	"github.com/elazarl/goproxy"
)

const (
	injectRoot     = "/__proxy_inject__/"
	backendPrefix  = injectRoot + "backend/"
	frontendPrefix = injectRoot + "frontend/"
	injectTag      = `<script src="/__proxy_inject__/frontend/inject.js"></script>`
)

func setCA(certPath, keyPath string) error {
	certPEM, err := os.ReadFile(certPath)
	if err != nil {
		return fmt.Errorf("read cert: %w", err)
	}
	keyPEM, err := os.ReadFile(keyPath)
	if err != nil {
		return fmt.Errorf("read key: %w", err)
	}

	gpCa, err := tls.X509KeyPair(certPEM, keyPEM)
	if err != nil {
		return fmt.Errorf("load keypair: %w", err)
	}
	gpCa.Leaf, err = x509.ParseCertificate(gpCa.Certificate[0])
	if err != nil {
		return fmt.Errorf("parse leaf cert: %w", err)
	}

	goproxy.GoproxyCa = gpCa
	caCfg := goproxy.TLSConfigFromCA(&gpCa)

	goproxy.OkConnect = &goproxy.ConnectAction{
		Action:    goproxy.ConnectAccept,
		TLSConfig: caCfg,
	}
	goproxy.MitmConnect = &goproxy.ConnectAction{
		Action:    goproxy.ConnectMitm,
		TLSConfig: caCfg,
	}
	goproxy.HTTPMitmConnect = &goproxy.ConnectAction{
		Action:    goproxy.ConnectHTTPMitm,
		TLSConfig: caCfg,
	}
	goproxy.RejectConnect = &goproxy.ConnectAction{
		Action:    goproxy.ConnectReject,
		TLSConfig: caCfg,
	}

	return nil
}

func handleRequest(req *http.Request, ctx *goproxy.ProxyCtx) (*http.Request, *http.Response) {
	if req.URL == nil {
		return req, nil
	}

	path := req.URL.Path

	if rest, ok := strings.CutPrefix(path, backendPrefix); ok {
		if rest == "" {
			rest = "/"
		} else {
			rest = "/" + rest
		}

		backendHost := os.Getenv("BACKEND_HOST")
		if backendHost == "" {
			backendHost = "localhost:8080"
		}

		req.URL.Scheme = "http"
		req.URL.Host = backendHost
		req.Host = backendHost
		req.URL.Path = rest

		ctx.Logf("rewrite backend -> %s", req.URL.String())
		return req, nil
	}

	if rest, ok := strings.CutPrefix(path, frontendPrefix); ok {
		if rest == "" {
			rest = "/"
		} else {
			rest = "/" + rest
		}

		frontendHost := os.Getenv("FRONTEND_HOST")
		if frontendHost == "" {
			frontendHost = "localhost:3000"
		}

		req.URL.Scheme = "http"
		req.URL.Host = frontendHost
		req.Host = frontendHost
		req.URL.Path = rest

		ctx.Logf("rewrite frontend -> %s", req.URL.String())
		return req, nil
	}

	return req, nil
}

func LastIndexFold(s, sep []byte) int {
	n := len(sep)
	if n == 0 {
		return len(s)
	}

	for i := len(s) - n; i >= 0; i-- {
		if bytes.EqualFold(s[i:i+n], sep) {
			return i
		}
	}
	return -1
}

func injectHTML(body []byte, ctx *goproxy.ProxyCtx) []byte {
	tag := []byte("</body>")
	inj := []byte(injectTag)

	if idx := LastIndexFold(body, tag); idx != -1 {
		newBody := make([]byte, 0, len(body)+len(inj))
		newBody = append(newBody, body[:idx]...)
		newBody = append(newBody, inj...)
		newBody = append(newBody, body[idx:]...)
		return newBody
	} else {
		newBody := make([]byte, 0, len(body)+len(inj))
		newBody = append(newBody, body...)
		newBody = append(newBody, inj...)
		return newBody
	}
}

func main() {
	addr := flag.String("addr", ":8000", "proxy listen address")
	certPath := flag.String("cert", "proxy_ca.crt", "CA certificate (PEM)")
	keyPath := flag.String("key", "proxy_ca.key", "CA private key (PEM)")
	verbose := flag.Bool("v", true, "log proxy requests")
	flag.Parse()

	if err := setCA(*certPath, *keyPath); err != nil {
		log.Fatalf("failed to load CA: %v", err)
	}

	proxy := goproxy.NewProxyHttpServer()
	proxy.Verbose = *verbose

	proxy.OnRequest().HandleConnect(goproxy.AlwaysMitm)
	proxy.OnRequest().DoFunc(handleRequest)
	proxy.OnResponse(goproxy.ContentTypeIs("text/html")).Do(
		goproxy.HandleBytes(func(b []byte, ctx *goproxy.ProxyCtx) []byte {
			return injectHTML(b, ctx)
		}),
	)

	log.Printf("listening on %s", *addr)
	log.Fatal(http.ListenAndServe(*addr, proxy))
}
