import json
import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, ForeignKey, UniqueConstraint, Float
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
    interaction_type = Column(String, default='buttons')   # buttons | reactions | select_menu
    single_select    = Column(Boolean, default=False)
    sort_order       = Column(Integer, default=0)
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


# ── Leveling ──────────────────────────────────────────────────────────────────

class LevelConfig(Base):
    __tablename__ = 'level_configs'
    guild_id           = Column(String, primary_key=True)
    enabled            = Column(Boolean, default=False)
    xp_min             = Column(Integer, default=15)
    xp_max             = Column(Integer, default=25)
    cooldown           = Column(Integer, default=60)
    levelup_mode       = Column(String, default='current')  # disabled/current/custom/dm
    levelup_channel_id = Column(String, nullable=True)
    levelup_message    = Column(Text, default='🎉 {user} hat **Level {level}** erreicht!')
    role_stack         = Column(Boolean, default=True)
    cmd_channels_json    = Column(Text, default='[]')  # allowed channels for /rank, /leaderboard; empty = everywhere
    voice_enabled        = Column(Boolean, default=False)
    voice_xp_min         = Column(Integer, default=10)
    voice_xp_max         = Column(Integer, default=20)
    voice_interval       = Column(Integer, default=5)   # minutes between voice XP grants
    voice_ignore_muted   = Column(Boolean, default=True)
    voice_ignore_deafened= Column(Boolean, default=True)

    @property
    def cmd_channels(self):
        return json.loads(self.cmd_channels_json or '[]')

    @cmd_channels.setter
    def cmd_channels(self, value):
        self.cmd_channels_json = json.dumps(value)


class UserLevel(Base):
    __tablename__ = 'user_levels'
    id         = Column(Integer, primary_key=True, autoincrement=True)
    guild_id   = Column(String, nullable=False)
    user_id    = Column(String, nullable=False)
    xp         = Column(Integer, default=0)
    level      = Column(Integer, default=0)
    last_xp_at = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint('guild_id', 'user_id', name='uq_user_level'),)


class LevelRole(Base):
    __tablename__ = 'level_roles'
    id       = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, nullable=False)
    level    = Column(Integer, nullable=False)
    role_id  = Column(String, nullable=False)


class XpMultiplierRole(Base):
    __tablename__ = 'xp_multiplier_roles'
    id         = Column(Integer, primary_key=True, autoincrement=True)
    guild_id   = Column(String, nullable=False)
    role_id    = Column(String, nullable=False)
    multiplier = Column(Float, default=2.0)


class XpMultiplierChannel(Base):
    __tablename__ = 'xp_multiplier_channels'
    id         = Column(Integer, primary_key=True, autoincrement=True)
    guild_id   = Column(String, nullable=False)
    channel_id = Column(String, nullable=False)
    multiplier = Column(Float, default=2.0)


class NoXpChannel(Base):
    __tablename__ = 'no_xp_channels'
    id         = Column(Integer, primary_key=True, autoincrement=True)
    guild_id   = Column(String, nullable=False)
    channel_id = Column(String, nullable=False)


class NoXpRole(Base):
    __tablename__ = 'no_xp_roles'
    id       = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, nullable=False)
    role_id  = Column(String, nullable=False)


def _migrate():
    from sqlalchemy import text, inspect as sa_inspect

    def _add_cols(table, cols_map):
        try:
            insp = sa_inspect(engine)
            if table not in insp.get_table_names():
                return
            existing = {c['name'] for c in insp.get_columns(table)}
        except Exception as e:
            print(f'[Migration] {table} nicht abrufbar: {e}')
            return
        for col, typedef in cols_map.items():
            if col not in existing:
                try:
                    with engine.connect() as conn:
                        conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {typedef}'))
                        conn.commit()
                    print(f'[Migration] {table}.{col} hinzugefügt')
                except Exception as e:
                    print(f'[Migration] Fehler {table}.{col}: {e}')

    _add_cols('level_configs', {
        'cmd_channels_json':     "TEXT DEFAULT '[]'",
        'voice_enabled':         'BOOLEAN DEFAULT false',
        'voice_xp_min':          'INTEGER DEFAULT 10',
        'voice_xp_max':          'INTEGER DEFAULT 20',
        'voice_interval':        'INTEGER DEFAULT 5',
        'voice_ignore_muted':    'BOOLEAN DEFAULT true',
        'voice_ignore_deafened': 'BOOLEAN DEFAULT true',
    })
    _add_cols('selfrole_messages', {
        'interaction_type': "TEXT DEFAULT 'buttons'",
        'single_select':    'BOOLEAN DEFAULT false',
        'sort_order':       'INTEGER DEFAULT 0',
    })


def init_db():
    Base.metadata.create_all(engine)
    _migrate()


def get_session():
    return SessionLocal()
