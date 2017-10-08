from datetime import datetime

from db import Session, User as DBUser
from util.hash import hasher, hasher_md5

from models import User, Contact, UserStatus, UserDetail, Group

class UserService:
	def __init__(self):
		# Dict[uuid, User]
		self._cache_by_uuid = {}
	
	def login(self, email, pwd):
		with Session() as sess:
			dbuser = sess.query(DBUser).filter(DBUser.email == email).one_or_none()
			if dbuser is None: return None
			if not hasher.verify(pwd, dbuser.password): return None
			return dbuser.uuid
	
	def login_md5(self, email, md5_hash):
		with Session() as sess:
			dbuser = sess.query(DBUser).filter(DBUser.email == email).one_or_none()
			if dbuser is None: return None
			if not hasher_md5.verify_hash(md5_hash, dbuser.password_md5): return None
			return dbuser.uuid
	
	def get_md5_salt(self, email):
		with Session() as sess:
			tmp = sess.query(DBUser.password_md5).filter(DBUser.email == email).one_or_none()
			password_md5 = tmp and tmp[0]
		if password_md5 is None: return None
		return hasher.extract_salt(password_md5)
	
	def update_date_login(self, uuid):
		with Session() as sess:
			sess.query(DBUser).filter(DBUser.uuid == uuid).update({
				'date_login': datetime.utcnow(),
			})
	
	def get_date_created(self, email):
		with Session() as sess:
			tmp = sess.query(DBUser.date_created).filter(DBUser.email == email).one_or_none()
			return tmp and (str(tmp[0])[0:19].replace(' ', 'T') + 'Z')
	
	def get_uuid(self, email):
		with Session() as sess:
			tmp = sess.query(DBUser.uuid).filter(DBUser.email == email).one_or_none()
			return tmp and tmp[0]
	
	def get_cid(self, email, decimal = False):
		uuid = self.get_uuid(email)
		cid = (uuid[0:8] + uuid[28:36]).upper()

		if (decimal is False):
			return cid

		# convert to decimal string
		cid = int(cid, 16)
		if cid > 0x7FFFFFFF:
			cid -= 0x100000000
		return str(cid)

	def get(self, uuid):
		if uuid is None: return None
		if uuid not in self._cache_by_uuid:
			self._cache_by_uuid[uuid] = self._get_uncached(uuid)
		return self._cache_by_uuid[uuid]
	
	def _get_uncached(self, uuid):
		with Session() as sess:
			dbuser = sess.query(DBUser).filter(DBUser.uuid == uuid).one_or_none()
			if dbuser is None: return None
			status = UserStatus(dbuser.name, dbuser.message)
			return User(dbuser.uuid, dbuser.email, dbuser.verified, status)
	
	def get_detail(self, uuid):
		with Session() as sess:
			dbuser = sess.query(DBUser).filter(DBUser.uuid == uuid).one_or_none()
			if dbuser is None: return None
			detail = UserDetail(dbuser.settings)
			for g in dbuser.groups:
				grp = Group(**g)
				detail.groups[grp.id] = grp
			for c in dbuser.contacts:
				ctc_head = self.get(c['uuid'])
				if ctc_head is None: continue
				status = UserStatus(c['name'], c['message'])
				ctc = Contact(ctc_head, set(c['groups']), c['lists'], status)
				detail.contacts[ctc.head.uuid] = ctc
		return detail
	
	def save_batch(self, to_save):
		with Session() as sess:
			for user, detail in to_save:
				dbuser = sess.query(DBUser).filter(DBUser.uuid == user.uuid).one()
				dbuser.name = user.status.name
				dbuser.message = user.status.message
				dbuser.settings = detail.settings
				dbuser.groups = [{ 'id': g.id, 'name': g.name } for g in detail.groups.values()]
				dbuser.contacts = [{
					'uuid': c.head.uuid, 'name': c.status.name, 'message': c.status.message,
					'lists': c.lists, 'groups': list(c.groups),
				} for c in detail.contacts.values()]
				sess.add(dbuser)
