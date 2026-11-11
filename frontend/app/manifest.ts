import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Local Image Search Engine",
    short_name: "LISE",
    description: "Image Search and Viewer App",
    start_url: "/",
    // これを指定することで、iOSに単体アプリとして起動するよう強制する
    display: "standalone", 
    background_color: "#18181b",
    theme_color: "#18181b",
    icons: [
      {
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: "/icon.png",
        sizes: "512x512",
        type: "image/png",
      },
    ],
  };
}