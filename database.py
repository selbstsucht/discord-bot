import json
import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, sessionmaker, relationship

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    # Railway PostgreSQL — fix postgres:// → postgresql://
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    engine = create_engine(DATABASE_URL)
else:
    DB_PATH = os.environ.get('DB_PATH', 'bot.db')
    engine = create_engine(f'sqlite:///{DB_PATH}', connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=True)


class Base(DeclarativeBase):
    pass


class WelcomeConfig(Base):
    __tablename__ = 'welcome_configs'
    guild_id   = Column(String, primary_key=True)
    channel_id = Column(String, nullable=True)
    message    = Column(Text, default='👋 Willkommen {user} auf **{server}**!')
    enabled    = Column(Boolean, default=False)


class GoodbyeConfig(Base):
    __tablename__ = 'goodbye_configs'
    guild_id   = Column(String, primary_key=True)
    channel_id = Column(String, nullable=True)
    message    = Column(Text, default='😢 {user} hat den Server verlassen.')
    enabled    = Column(Boolean, default=False)


class AutoRoleConfig(Base):
    __tablename__ = 'autorole_configs'
    guild_id       = Column(String, primary_key=True)
    role_ids_json  = Column(Text, default='[]')
    enabled        = Column(Boolean, default=False)

    @property
    def role_ids(self):
        return json.loads(self.role_ids_json or '[]')

    @role_ids.setter
    def role_ids(self, value):
        self.role_ids_json = json.dumps(value)


class SelfRoleMessage(Base):
    __tablename__ = 'selfrole_messages'
    id               = Column(Integer, primary_key=True, autoincrement=True)
    guild_id         = Column(String, nullable=False)
    channel_id       = Column(String, nullable=True)
    message_id       = Column(String, nullable=True)
    embed_title      = Column(String, default='Self Roles')
    embed_description= Column(Text, default='Klicke auf einen Button um eine Rolle zu erhalten!')
    embed_color      = Column(Integer, default=0x5865F2)
    embed_image_url  = Column(String, nullable=True)
    buttons          = relationship('SelfRoleButton', back_populates='sr_message',
                                    cascade='all, delete-orphan')


class SelfRoleButton(Base):
    __tablename__ = 'selfrole_buttons'
    id              = Column(Integer, primary_key=True, autoincrement=True)
    message_id_fk   = Column(Integer, ForeignKey('selfrole_messages.id', ondelete='CASCADE'))
    role_id         = Column(String, nullable=False)
    label           = Column(String, nullable=False)
    emoji           = Column(String, nullable=True)
    style           = Column(String, default='primary')
    sr_message      = relationship('SelfRoleMessage', back_populates='buttons')


def init_db():
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()
