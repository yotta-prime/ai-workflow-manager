const path = require('path');

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  webpack: (config, { isServer }) => {
    if (isServer) {
      config.resolve.alias['isomorphic-dompurify'] = path.resolve(__dirname, 'lib/dompurify-ssr.js');
    }
    return config;
  },
};

module.exports = nextConfig;
