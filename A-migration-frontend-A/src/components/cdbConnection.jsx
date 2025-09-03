import PouchDB from 'pouchdb-browser';
const couchdbUrl = "http://couchdb-route-open-db.apps.itz-47ubpb.infra01-lb.dal14.techzone.ibm.com"
; 
const dbName = "transaction";
// if (!couchdbUrl) {
//   throw new Error("REACT_APP_COUCHDB_URL is not defined in .env");
// }
const db = new PouchDB(
  `https://${couchdbUrl.replace(/\/$/, '')}/${dbName}`,
  {
    skip_setup: false
  }
);
// Optional: test connection
db.info()
  .then(info => console.log("DB info:", info))
  .catch(err => console.error("DB connection error:", err));
export default db;
