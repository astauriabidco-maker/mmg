package com.atelier.v1.data

import android.content.Context
import androidx.room.*
import androidx.room.RoomDatabase

@Entity(tableName = "pending_actions")
data class PendingAction(
    @PrimaryKey(autoGenerate = true) val id: Int = 0,
    val type: String, // START, STOP, PAUSE
    val payloadJson: String,
    val createdAt: Long = System.currentTimeMillis()
)

@Dao
interface PendingActionDao {
    @Query("SELECT * FROM pending_actions ORDER BY createdAt ASC")
    suspend fun getAll(): List<PendingAction>

    @Insert
    suspend fun insert(action: PendingAction)

    @Delete
    suspend fun delete(action: PendingAction)
}

@Database(entities = [PendingAction::class], version = 1)
abstract class AppDatabase : RoomDatabase() {
    abstract fun pendingActionDao(): PendingActionDao

    companion object {
        @Volatile
        private var INSTANCE: AppDatabase? = null

        fun getDatabase(context: Context): AppDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "atelier_database"
                ).build()
                INSTANCE = instance
                instance
            }
        }
    }
}
