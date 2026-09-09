module.exports = {
  sanitize: (str) => (typeof str === 'string' ? str : ''),
  default: {
    sanitize: (str) => (typeof str === 'string' ? str : ''),
  },
};
